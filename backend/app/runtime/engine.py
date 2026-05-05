from datetime import datetime, timezone

from sqlmodel import select

from app.brokers.base import BrokerOrder, BrokerPort
from app.brokers.sim.broker import SimBroker
from app.brokers.webull.client import WebullBroker
from app.config import settings
from app.llm.claude import ClaudeReasoningClient
from app.market_data.provider import MockMarketDataProvider, WebullMarketDataProvider
from app.risk.manager import RiskManager
from app.storage.db import get_session
from app.storage.models import AgentEvent, Fill, Order, OrderIntent, Position, RiskDecision, Signal
from app.trading.contracts import ContractSelector
from app.trading.exits import emergency_tick_drop_triggered
from app.trading.strategy import StrategyEngine


class TradingRuntime:
    def __init__(self):
        self.running = False
        self.market_data = self._build_market_data()
        self.strategy = StrategyEngine()
        self.selector = ContractSelector()
        self.risk = RiskManager()
        self.broker = self._build_broker()
        self.claude = ClaudeReasoningClient()
        self.symbol = settings.trade_symbol.upper()

    def _build_broker(self) -> BrokerPort:
        if settings.app_mode == 'SIM':
            return SimBroker()
        if settings.app_mode in {'WEBULL_PAPER', 'WEBULL_LIVE'}:
            return WebullBroker(mode=settings.app_mode)
        raise RuntimeError(f'Unsupported app mode: {settings.app_mode}')

    def _build_market_data(self):
        if settings.app_mode == 'SIM':
            return MockMarketDataProvider()
        if settings.app_mode in {'WEBULL_PAPER', 'WEBULL_LIVE'}:
            return WebullMarketDataProvider(mode=settings.app_mode)
        raise RuntimeError(f'Unsupported app mode: {settings.app_mode}')

    async def run_signal_cycle(self) -> None:
        now = datetime.now(timezone.utc)
        if self.risk.reset_for_new_day(now):
            self._event('risk_reset', 'daily_risk_counters_reset')
        ctx = self.market_data.latest_signal_context(self.symbol)
        signal = self.strategy.evaluate(ctx)

        if not signal:
            self._event('signal', 'no_signal')
            return

        objective = {
            'daily_profit_cap_usd': settings.max_daily_profit,
            'daily_loss_cap_usd': settings.max_daily_loss,
            'max_trades_per_day': settings.max_trades_per_day,
            'max_loss_per_trade_pct': settings.max_loss_per_trade_pct,
            'mandate': 'Favor quality over quantity; flag chop and sudden regime change; never suggest bypassing risk.',
        }
        llm = await self.claude.explain(
            {'objective': objective, 'signal': signal.__dict__, 'context': ctx.__dict__}
        )
        signal.confidence = float(llm.get('confidence', 0.5))

        if settings.chop_blocks_entry and bool(llm.get('chop_warning')):
            self._event('llm', 'entry_blocked_chop')
            return
        if settings.min_entry_confidence > 0 and signal.confidence < settings.min_entry_confidence:
            self._event('llm', f'entry_blocked_low_confidence:{signal.confidence:.2f}')
            return

        chain = self.market_data.option_chain(self.symbol)
        contract = self.selector.select(chain, signal.side)
        if not contract:
            self._event('contract', 'no_valid_contract')
            return

        decision = self.risk.approve_entry(now)

        with get_session() as session:
            db_signal = Signal(timestamp=now, symbol=self.symbol, side=signal.side, reason=signal.reason, confidence=signal.confidence)
            session.add(db_signal)
            session.flush()
            session.add(RiskDecision(timestamp=now, approved=decision.approved, reason=decision.reason, signal_id=db_signal.id))

            if not decision.approved:
                session.commit()
                self._event('risk', f'denied:{decision.reason}')
                return

            limit_price = round((contract.bid + contract.ask) / 2, 2)
            side = 'BUY_CALL' if signal.side == 'CALL' else 'BUY_PUT'
            intent = OrderIntent(timestamp=now, symbol=self.symbol, option_symbol=contract.option_symbol, side=side, qty=1, limit_price=limit_price, status='SUBMITTED')
            session.add(intent)
            try:
                result = self.broker.place_limit_order(
                    BrokerOrder(
                        contract.option_symbol,
                        side,
                        1,
                        limit_price,
                        underlying=self.symbol,
                        expiry=contract.expiry,
                        strike=contract.strike,
                        option_type='CALL' if signal.side == 'CALL' else 'PUT',
                    )
                )
            except Exception as exc:
                session.add(AgentEvent(timestamp=now, event_type='broker_error', message=str(exc)))
                session.commit()
                return
            order = Order(
                timestamp=now,
                broker_order_id=result.broker_order_id,
                option_symbol=contract.option_symbol,
                underlying=self.symbol,
                expiry=contract.expiry,
                strike=contract.strike,
                option_type='CALL' if signal.side == 'CALL' else 'PUT',
                side=side,
                qty=1,
                limit_price=limit_price,
                status=result.status,
            )
            session.add(order)
            session.commit()

        self._event('order', f'placed:{contract.option_symbol}')

    def _position_mark(self, pos: Position) -> float:
        if settings.app_mode == 'SIM':
            return pos.mark_price * 1.02
        return self.market_data.option_mark(pos.option_symbol)

    def run_monitor_cycle(self) -> None:
        now = datetime.now(timezone.utc)
        if self.risk.reset_for_new_day(now):
            self._event('risk_reset', 'daily_risk_counters_reset')
        with get_session() as session:
            open_orders = session.exec(select(Order).where(Order.status == 'OPEN')).all()
            for order in open_orders:
                age_sec = (now - order.timestamp).total_seconds()
                if age_sec >= settings.order_timeout_seconds:
                    self.broker.cancel_order(order.broker_order_id)
                    order.status = 'CANCELED'
                    continue
                filled, fill_price = self.broker.try_fill(order.broker_order_id, order.limit_price)
                if filled:
                    order.status = 'FILLED'
                    session.add(Fill(timestamp=now, order_id=order.id, fill_price=fill_price, qty=order.qty))
                    side_is_call = order.side.endswith('CALL')
                    session.add(
                        Position(
                            option_symbol=order.option_symbol,
                            underlying=order.underlying,
                            expiry=order.expiry,
                            strike=order.strike,
                            option_type=order.option_type or ('CALL' if side_is_call else 'PUT'),
                            qty=order.qty,
                            avg_price=fill_price,
                            mark_price=fill_price,
                            opened_at=now,
                        )
                    )

            positions = session.exec(select(Position).where(Position.status == 'OPEN')).all()
            for pos in positions:
                mark = self._position_mark(pos)

                emergency = emergency_tick_drop_triggered(
                    pos.last_mark_price, mark, settings.sudden_option_drop_pct
                )
                pnl_pct = (mark - pos.avg_price) / pos.avg_price
                pos.mark_price = mark
                pos.unrealized_pnl = (mark - pos.avg_price) * pos.qty * 100

                stop_loss = -settings.max_loss_per_trade_pct
                take_profit = settings.take_profit_pct
                if emergency or pnl_pct <= stop_loss or pnl_pct >= take_profit:
                    exit_reason = (
                        'emergency_tick_drop'
                        if emergency
                        else ('stop_loss' if pnl_pct <= stop_loss else 'take_profit')
                    )
                    if settings.app_mode != 'SIM':
                        sell_side = 'SELL_CALL' if pos.option_type == 'CALL' else 'SELL_PUT'
                        exit_result = self.broker.place_limit_order(
                            BrokerOrder(
                                option_symbol=pos.option_symbol,
                                side=sell_side,
                                qty=pos.qty,
                                limit_price=round(mark, 2),
                                underlying=pos.underlying,
                                expiry=pos.expiry,
                                strike=pos.strike,
                                option_type=pos.option_type,
                            )
                        )
                        self._event('exit_order', f'submitted:{exit_result.broker_order_id}')
                    pos.status = 'CLOSED'
                    pos.closed_at = now
                    realized = (mark - pos.avg_price) * pos.qty * 100
                    pos.realized_pnl = realized
                    self.risk.on_trade_close(realized)
                    self._event('position_exit', exit_reason)
                else:
                    pos.last_mark_price = mark
            session.commit()

    def account_snapshot(self) -> dict:
        with get_session() as session:
            positions = session.exec(select(Position)).all()
            open_positions = [p for p in positions if p.status == 'OPEN']
            closed_positions = [p for p in positions if p.status == 'CLOSED']
            realized = sum(p.realized_pnl for p in closed_positions)
            unrealized = sum(p.unrealized_pnl for p in open_positions)
        return {
            'mode': settings.app_mode,
            'symbol': self.symbol,
            'runtime_running': self.running,
            'open_positions': len(open_positions),
            'closed_positions': len(closed_positions),
            'realized_pnl': round(realized, 2),
            'unrealized_pnl': round(unrealized, 2),
        }

    def recent_trades(self) -> list[dict]:
        with get_session() as session:
            closed_positions = session.exec(
                select(Position).where(Position.status == 'CLOSED').order_by(Position.id.desc()).limit(50)
            ).all()
        return [
            {
                'option_symbol': p.option_symbol,
                'qty': p.qty,
                'avg_price': p.avg_price,
                'exit_price': p.mark_price,
                'realized_pnl': p.realized_pnl,
                'opened_at': p.opened_at,
                'closed_at': p.closed_at,
            }
            for p in closed_positions
        ]

    def promotion_gate(self) -> dict:
        with get_session() as session:
            closed_positions = session.exec(select(Position).where(Position.status == 'CLOSED')).all()
        count = len(closed_positions)
        if count == 0:
            return {'eligible': False, 'reason': 'no_closed_trades', 'metrics': {'trade_count': 0}}

        wins = [p for p in closed_positions if p.realized_pnl > 0]
        losses = [p for p in closed_positions if p.realized_pnl < 0]
        gross_profit = sum(p.realized_pnl for p in wins)
        gross_loss = abs(sum(p.realized_pnl for p in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss else 99.0
        win_rate = len(wins) / count

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for p in sorted(closed_positions, key=lambda x: x.closed_at or x.opened_at):
            equity += p.realized_pnl
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)

        metrics = {
            'trade_count': count,
            'win_rate': round(win_rate, 4),
            'profit_factor': round(profit_factor, 4),
            'max_drawdown': round(max_drawdown, 4),
        }
        eligible = (
            count >= 50
            and win_rate >= 0.45
            and profit_factor >= 1.2
            and max_drawdown <= 0.08
            and self.risk.state.consecutive_losses < settings.max_consecutive_losses
        )
        return {'eligible': eligible, 'metrics': metrics}

    def preflight(self) -> dict:
        checks: dict[str, dict] = {}

        checks['mode'] = {'ok': settings.app_mode in {'SIM', 'WEBULL_PAPER', 'WEBULL_LIVE'}, 'value': settings.app_mode}
        checks['trade_symbol'] = {'ok': bool(self.symbol), 'value': self.symbol}
        checks['option_watchlist'] = {
            'ok': bool(settings.option_watchlist),
            'value': [x.strip() for x in settings.option_watchlist.split(',') if x.strip()],
        }
        checks['risk_limits'] = {
            'ok': settings.max_daily_loss > 0 and settings.max_daily_profit > 0 and settings.max_trades_per_day > 0,
            'value': {
                'max_trades_per_day': settings.max_trades_per_day,
                'max_daily_loss': settings.max_daily_loss,
                'max_daily_profit': settings.max_daily_profit,
                'min_entry_confidence': settings.min_entry_confidence,
                'chop_blocks_entry': settings.chop_blocks_entry,
                'sudden_option_drop_pct': settings.sudden_option_drop_pct,
            },
        }
        checks['trading_enabled'] = {'ok': settings.trading_enabled, 'value': settings.trading_enabled}

        if settings.app_mode in {'WEBULL_PAPER', 'WEBULL_LIVE'}:
            try:
                _ = self.market_data.latest_signal_context(self.symbol)
                checks['webull_market_data'] = {'ok': True, 'value': 'connected'}
            except Exception as exc:
                checks['webull_market_data'] = {'ok': False, 'value': str(exc)}
        else:
            checks['webull_market_data'] = {'ok': True, 'value': 'not_required_in_sim'}

        ready = all(item.get('ok', False) for item in checks.values())
        return {'ready': ready, 'checks': checks}

    def _event(self, event_type: str, message: str) -> None:
        with get_session() as session:
            session.add(AgentEvent(timestamp=datetime.now(timezone.utc), event_type=event_type, message=message))
            session.commit()


runtime = TradingRuntime()
