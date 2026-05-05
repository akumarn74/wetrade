import pytest
from sqlmodel import select

from app.config import Settings
from app import config as config_module
from app.runtime import engine as engine_module
from app.runtime.engine import TradingRuntime
from app.storage.db import get_session, init_db
from app.storage.models import Order, Signal


@pytest.mark.asyncio
async def test_signal_to_order_pipeline(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    init_db()
    runtime = TradingRuntime()
    runtime.risk.state.trades_today = 0
    await runtime.run_signal_cycle()
    with get_session() as session:
        signals = session.exec(select(Signal)).all()
        orders = session.exec(select(Order)).all()
    assert len(signals) >= 1
    assert len(orders) == 0  # disabled trading by default
