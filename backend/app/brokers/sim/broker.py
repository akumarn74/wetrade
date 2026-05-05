from datetime import datetime

from app.brokers.base import BrokerOrder, BrokerOrderResult, BrokerPort


class SimBroker(BrokerPort):
    def __init__(self):
        self.orders: dict[str, dict] = {}

    def place_limit_order(self, order: BrokerOrder) -> BrokerOrderResult:
        order_id = f"sim-{len(self.orders)+1}"
        self.orders[order_id] = {
            'created_at': datetime.utcnow(),
            'order': order,
            'status': 'OPEN',
        }
        return BrokerOrderResult(broker_order_id=order_id, status='OPEN')

    def cancel_order(self, broker_order_id: str) -> None:
        if broker_order_id in self.orders:
            self.orders[broker_order_id]['status'] = 'CANCELED'

    def try_fill(self, broker_order_id: str, mark_price: float) -> tuple[bool, float]:
        state = self.orders.get(broker_order_id)
        if not state or state['status'] != 'OPEN':
            return False, 0.0
        order = state['order']
        if order.side in ('BUY_CALL', 'BUY_PUT') and mark_price <= order.limit_price:
            state['status'] = 'FILLED'
            return True, mark_price
        if order.side in ('SELL_CALL', 'SELL_PUT') and mark_price >= order.limit_price:
            state['status'] = 'FILLED'
            return True, mark_price
        return False, 0.0
