"""
Scenario tests: mock samples → strategy → selector → (optional) full SIM signal cycle.

These tests document expected behavior and known gaps when something regresses.
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
from app.storage.models import AgentEvent, Fill, Order, OrderIntent, Position, RiskDecision, Signal
from app.trading.contracts import ContractSelector
from app.trading.strategy import StrategyEngine
from app.trading.types import SignalContext

from tests.fixtures.mock_market_samples import (
    chain_liquid_spx_calls_and_puts,
    chain_only_wide_spread_calls,
    ctx_call_but_volume_not_expanding,
    ctx_call_trend_volume_spike,
    ctx_chop_no_clear_trend,
    ctx_put_trend_volume_spike,
)


class StubMarketDataProvider:
    """Injectable provider for deterministic integration tests."""

    def __init__(self, ctx: SignalContext, chain: list):
        self._ctx = ctx
        self._chain = chain

    def latest_signal_context(self, symbol: str = 'SPX'):
        return self._ctx

    def option_chain(self, symbol: str = 'SPX'):
        return self._chain


def _clear_trading_tables() -> None:
    """Remove rows so scenario tests do not depend on global DB order."""
    with get_session() as session:
        for model in (AgentEvent, Fill, Position, Order, OrderIntent, RiskDecision, Signal):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()


@pytest.mark.parametrize(
    'sample_factory,expected_side',
    [
        (ctx_call_trend_volume_spike, 'CALL'),
        (ctx_put_trend_volume_spike, 'PUT'),
    ],
)
def test_strategy_fires_on_documented_trend_samples(sample_factory, expected_side):
    engine = StrategyEngine()
    sig = engine.evaluate(sample_factory('SPX'))
    assert sig is not None
    assert sig.side == expected_side


@pytest.mark.parametrize(
    'sample_factory',
    [ctx_call_but_volume_not_expanding, ctx_chop_no_clear_trend],
)
def test_strategy_returns_none_when_rules_fail(sample_factory):
    engine = StrategyEngine()
    assert engine.evaluate(sample_factory('SPX')) is None


def test_contract_selector_picks_tightest_spread_call():
    selector = ContractSelector()
    picked = selector.select(chain_liquid_spx_calls_and_puts(), 'CALL')
    assert picked is not None
    assert picked.right == 'C'
    assert picked.option_symbol == 'SPX-2026-01-10-5000-C'


def test_contract_selector_rejects_wide_spread():
    selector = ContractSelector()
    assert selector.select(chain_only_wide_spread_calls(), 'CALL') is None


@pytest.mark.asyncio
async def test_full_signal_cycle_sim_places_order_with_stub_data(monkeypatch):
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
        return_value={
            'confidence': 0.82,
            'chop_warning': False,
            'rationale': 'mock',
            'anomaly_flags': [],
        }
    )

    await runtime.run_signal_cycle()

    with get_session() as session:
        orders = session.exec(select(Order).order_by(Order.id.desc())).all()
        events = session.exec(select(AgentEvent)).all()

    assert len(orders) >= 1
    assert orders[0].status == 'OPEN'
    assert orders[0].underlying == 'SPX'
    assert 'placed' in ' '.join(e.message for e in events if e.event_type == 'order')


@pytest.mark.asyncio
async def test_full_signal_cycle_stops_at_contract_filter(monkeypatch):
    """CALL signal fires but chain has no valid contract → no order."""
    monkeypatch.setenv('APP_MODE', 'SIM')
    monkeypatch.setenv('TRADING_ENABLED', 'true')
    monkeypatch.setenv('TRADE_SYMBOL', 'SPX')
    monkeypatch.setenv('MIN_ENTRY_CONFIDENCE', '0')

    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    risk_module.settings = config_module.settings

    monkeypatch.setattr(RiskManager, '_within_time_window', lambda self, now: True)

    init_db()
    _clear_trading_tables()
    runtime = TradingRuntime()
    runtime.market_data = StubMarketDataProvider(
        ctx_call_trend_volume_spike('SPX'),
        chain_only_wide_spread_calls(),
    )
    runtime.claude.explain = AsyncMock(return_value={'confidence': 0.5})

    await runtime.run_signal_cycle()

    with get_session() as session:
        orders = session.exec(select(Order)).all()
    assert len(orders) == 0


def test_documented_gap_trailing_stop_config_not_wired():
    """TRAIL_ACTIVATION_PCT exists but monitor loop does not implement trailing exits yet."""
    import inspect

    from app.runtime import engine as eng

    src = inspect.getsource(eng.TradingRuntime.run_monitor_cycle)
    assert 'trail_activation' not in src


def test_risk_session_window_behavior_snapshot_utc():
    """
    Window math uses now.hour/minute against MARKET_OPEN_TIME/CLOSE strings with no timezone layer.
    This snapshot documents behavior for one UTC instant; treat as regression signal if changed.
    """
    cfg = Settings()
    config_module.settings = cfg
    risk_module.settings = cfg
    rm = RiskManager()
    now = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    rm.reset_for_new_day(now)
    assert rm._within_time_window(now) is True
