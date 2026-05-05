"""
Tests aligned with trading objective: ~$100/day cap, quality entries, skip bad tape,
strict exit on sudden option mark drop.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from app import config as config_module
from app.config import Settings
from app.risk import manager as risk_module
from app.risk.manager import RiskManager
from app.runtime import engine as engine_module
from app.runtime.engine import TradingRuntime
from app.storage.db import get_session, init_db
from app.storage.models import AgentEvent, Order, Position
from app.trading.exits import emergency_tick_drop_triggered

from tests.test_algorithm_scenarios import StubMarketDataProvider, _clear_trading_tables
from tests.fixtures.mock_market_samples import chain_liquid_spx_calls_and_puts, ctx_call_trend_volume_spike


@pytest.mark.parametrize(
    'prev,mark,pct,expected',
    [
        (2.0, 1.7, 0.12, True),
        (2.0, 1.77, 0.12, False),
        (None, 1.5, 0.12, False),
    ],
)
def test_emergency_tick_drop_scenarios(prev, mark, pct, expected):
    assert emergency_tick_drop_triggered(prev, mark, pct) is expected


@pytest.mark.asyncio
async def test_objective_chop_blocks_entry_no_order(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    monkeypatch.setenv('TRADING_ENABLED', 'true')
    monkeypatch.setenv('TRADE_SYMBOL', 'SPX')
    monkeypatch.setenv('MIN_ENTRY_CONFIDENCE', '0')
    monkeypatch.setenv('CHOP_BLOCKS_ENTRY', 'true')

    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    risk_module.settings = config_module.settings
    monkeypatch.setattr(RiskManager, '_within_time_window', lambda self, now: True)

    init_db()
    _clear_trading_tables()
    runtime = TradingRuntime()
    runtime.market_data = StubMarketDataProvider(
        ctx_call_trend_volume_spike('SPX'),
        chain_liquid_spx_calls_and_puts(),
    )
    runtime.claude.explain = AsyncMock(
        return_value={'confidence': 0.9, 'chop_warning': True, 'rationale': 'chop', 'anomaly_flags': []}
    )

    await runtime.run_signal_cycle()

    with get_session() as session:
        orders = session.exec(select(Order)).all()
        events = [e for e in session.exec(select(AgentEvent)).all() if e.event_type == 'llm']
    assert len(orders) == 0
    assert any('chop' in e.message for e in events)


@pytest.mark.asyncio
async def test_objective_low_confidence_blocks_entry(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    monkeypatch.setenv('TRADING_ENABLED', 'true')
    monkeypatch.setenv('TRADE_SYMBOL', 'SPX')
    monkeypatch.setenv('MIN_ENTRY_CONFIDENCE', '0.7')
    monkeypatch.setenv('CHOP_BLOCKS_ENTRY', 'false')

    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    risk_module.settings = config_module.settings
    monkeypatch.setattr(RiskManager, '_within_time_window', lambda self, now: True)

    init_db()
    _clear_trading_tables()
    runtime = TradingRuntime()
    runtime.market_data = StubMarketDataProvider(
        ctx_call_trend_volume_spike('SPX'),
        chain_liquid_spx_calls_and_puts(),
    )
    runtime.claude.explain = AsyncMock(
        return_value={'confidence': 0.4, 'chop_warning': False, 'rationale': 'weak', 'anomaly_flags': []}
    )

    await runtime.run_signal_cycle()

    with get_session() as session:
        orders = session.exec(select(Order)).all()
    assert len(orders) == 0


def test_objective_daily_profit_cap_stops_new_entries(monkeypatch):
    monkeypatch.setenv('MAX_DAILY_PROFIT', '100')
    monkeypatch.setenv('TRADING_ENABLED', 'true')
    config_module.settings = Settings()
    risk_module.settings = config_module.settings

    rm = RiskManager()
    rm.state.daily_realized_pnl = 100.0
    from datetime import datetime, timezone

    d = rm.approve_entry(datetime.now(timezone.utc))
    assert d.approved is False
    assert d.reason == 'max_daily_profit_reached'


def test_monitor_emergency_exit_on_sudden_tick_drop(monkeypatch):
    """Second monitor tick drops mark enough vs prior tick → emergency_tick_drop exit."""
    monkeypatch.setenv('APP_MODE', 'SIM')
    monkeypatch.setenv('SUDDEN_OPTION_DROP_PCT', '0.10')
    monkeypatch.setenv('MIN_ENTRY_CONFIDENCE', '0')

    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    risk_module.settings = config_module.settings

    init_db()
    _clear_trading_tables()

    marks = iter([2.0, 1.75])

    def fake_position_mark(self, pos):
        return next(marks)

    monkeypatch.setattr(TradingRuntime, '_position_mark', fake_position_mark)

    runtime = TradingRuntime()
    now = datetime.now(timezone.utc)
    with get_session() as session:
        session.add(
            Position(
                option_symbol='SPX-TEST-C',
                underlying='SPX',
                expiry='2026-01-10',
                strike=5000.0,
                option_type='CALL',
                qty=1,
                avg_price=2.0,
                mark_price=2.0,
                last_mark_price=None,
                opened_at=now,
                status='OPEN',
            )
        )
        session.commit()

    runtime.run_monitor_cycle()
    runtime.run_monitor_cycle()

    with get_session() as session:
        closed = session.exec(select(Position).where(Position.status == 'CLOSED')).all()
        exits = [e for e in session.exec(select(AgentEvent)).all() if e.event_type == 'position_exit']
    assert len(closed) == 1
    assert any('emergency_tick_drop' in e.message for e in exits)
