from dataclasses import dataclass
from datetime import date, datetime, time

from app.config import settings


@dataclass
class RiskState:
    trades_today: int = 0
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    halted_reason: str = ''
    last_reset_day: date | None = None


@dataclass
class RiskDecisionResult:
    approved: bool
    reason: str


class RiskManager:
    def __init__(self):
        self.state = RiskState()

    def _within_time_window(self, now: datetime) -> bool:
        open_t = time.fromisoformat(settings.market_open_time)
        close_t = time.fromisoformat(settings.market_close_time)
        mins_from_open = (now.hour * 60 + now.minute) - (open_t.hour * 60 + open_t.minute)
        mins_to_close = (close_t.hour * 60 + close_t.minute) - (now.hour * 60 + now.minute)
        return mins_from_open >= settings.no_trade_first_minutes and mins_to_close >= settings.no_trade_last_minutes

    def reset_for_new_day(self, now: datetime) -> bool:
        today = now.date()
        if self.state.last_reset_day is None:
            self.state.last_reset_day = today
            return False
        if self.state.last_reset_day != today:
            self.state.trades_today = 0
            self.state.daily_realized_pnl = 0.0
            self.state.consecutive_losses = 0
            self.state.halted_reason = ''
            self.state.last_reset_day = today
            return True
        return False

    def approve_entry(self, now: datetime) -> RiskDecisionResult:
        if not settings.trading_enabled:
            self.state.halted_reason = 'trading_disabled'
            return RiskDecisionResult(False, 'trading_disabled')
        if self.state.trades_today >= settings.max_trades_per_day:
            self.state.halted_reason = 'max_trades_reached'
            return RiskDecisionResult(False, 'max_trades_reached')
        if self.state.daily_realized_pnl <= -settings.max_daily_loss:
            self.state.halted_reason = 'max_daily_loss_reached'
            return RiskDecisionResult(False, 'max_daily_loss_reached')
        if self.state.daily_realized_pnl >= settings.max_daily_profit:
            self.state.halted_reason = 'max_daily_profit_reached'
            return RiskDecisionResult(False, 'max_daily_profit_reached')
        if self.state.consecutive_losses >= settings.max_consecutive_losses:
            self.state.halted_reason = 'max_consecutive_losses_reached'
            return RiskDecisionResult(False, 'max_consecutive_losses_reached')
        if not self._within_time_window(now):
            self.state.halted_reason = 'outside_trade_window'
            return RiskDecisionResult(False, 'outside_trade_window')
        self.state.halted_reason = ''
        return RiskDecisionResult(True, 'approved')

    def on_trade_close(self, pnl: float) -> None:
        self.state.daily_realized_pnl += pnl
        self.state.trades_today += 1
        self.state.consecutive_losses = self.state.consecutive_losses + 1 if pnl < 0 else 0
