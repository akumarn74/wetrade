from datetime import datetime
from uuid import uuid4

from app.brokers.base import BrokerOrder, BrokerOrderResult, BrokerPort
from app.config import settings
from app.integrations.webull_client import WebullAPIClient


class WebullBroker(BrokerPort):
    """
    Phase 2 adapter surface. For now:
    - WEBULL_PAPER uses deterministic local paper execution.
    - WEBULL_LIVE attempts SDK wiring and raises a clear error until real SDK
      auth/order implementation is completed with account credentials.
    """

    def __init__(self, mode: str):
        self.mode = mode
        self.orders: dict[str, dict] = {}
        self.api = WebullAPIClient().api
        self.account_id = settings.webull_account_id

    def place_limit_order(self, order: BrokerOrder) -> BrokerOrderResult:
        side = 'BUY' if order.side.startswith('BUY') else 'SELL'
        option_type = order.option_type or ('CALL' if order.side.endswith('CALL') else 'PUT')
        underlying = order.underlying
        expiry = order.expiry
        strike = order.strike
        if not underlying or not expiry or strike is None:
            raise RuntimeError('BrokerOrder missing underlying/expiry/strike required for Webull option order')
        client_order_id = uuid4().hex
        new_orders = [
            {
                'client_order_id': client_order_id,
                'combo_type': 'NORMAL',
                'order_type': 'LIMIT',
                'quantity': str(order.qty),
                'limit_price': str(order.limit_price),
                'option_strategy': 'SINGLE',
                'side': side,
                'time_in_force': 'DAY',
                'entrust_type': 'QTY',
                'orders': [
                    {
                        'side': side,
                        'quantity': str(order.qty),
                        'symbol': underlying,
                        'strike_price': str(strike),
                        'init_exp_date': expiry,
                        'instrument_type': 'OPTION',
                        'option_type': option_type,
                        'market': 'US',
                    }
                ],
            }
        ]
        self.api.order_v2.place_option(self.account_id, new_orders)

        order_id = client_order_id
        self.orders[order_id] = {
            'created_at': datetime.utcnow(),
            'order': order,
            'status': 'OPEN',
        }
        return BrokerOrderResult(broker_order_id=order_id, status='OPEN')

    def cancel_order(self, broker_order_id: str) -> None:
        self.api.order_v2.cancel_option(self.account_id, broker_order_id)
        if broker_order_id in self.orders:
            self.orders[broker_order_id]['status'] = 'CANCELED'

    def try_fill(self, broker_order_id: str, mark_price: float) -> tuple[bool, float]:
        state = self.orders.get(broker_order_id)
        if not state:
            return False, 0.0
        if state['status'] == 'FILLED':
            return True, mark_price

        detail = self.api.order_v2.get_order_detail(self.account_id, broker_order_id).json()
        order_status = str(detail.get('status') or detail.get('order_status') or '').upper()
        if order_status in {'FILLED', 'EXECUTED', 'COMPLETED'}:
            state['status'] = 'FILLED'
            avg_fill = float(detail.get('avg_fill_price') or detail.get('filled_avg_price') or mark_price)
            return True, avg_fill
        if order_status in {'CANCELED', 'REJECTED', 'EXPIRED'}:
            state['status'] = 'CANCELED'
        return False, 0.0
