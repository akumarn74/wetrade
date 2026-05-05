from datetime import datetime, timezone

from app.risk.manager import RiskManager
from app.trading.strategy import StrategyEngine
from app.trading.types import SignalContext


def test_call_signal_rules():
    engine = StrategyEngine()
    signal = engine.evaluate(
        SignalContext(
            symbol='SPY',
            price=101,
            vwap=100,
            prev_high=100.5,
            prev_low=99,
            ma5=101,
            ma10=100,
            ma20=99,
            volume=2000,
            avg_volume=1000,
            day_high=102,
            day_low=98,
        )
    )
    assert signal is not None
    assert signal.side == 'CALL'


def test_risk_denies_when_disabled():
    rm = RiskManager()
    decision = rm.approve_entry(datetime.now(timezone.utc))
    assert decision.approved is False
