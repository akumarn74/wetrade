from datetime import datetime, timezone

from app.config import Settings
from app import config as config_module
from app.runtime import engine as engine_module
from app.runtime.engine import TradingRuntime
from app.storage.db import get_session, init_db
from app.storage.models import Position


def test_promotion_gate_requires_volume(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    init_db()
    runtime = TradingRuntime()
    gate = runtime.promotion_gate()
    assert gate["eligible"] is False


def test_promotion_gate_metrics_shape(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    config_module.settings = Settings()
    engine_module.settings = config_module.settings
    init_db()
    runtime = TradingRuntime()
    now = datetime.now(timezone.utc)
    with get_session() as session:
        for i in range(10):
            session.add(
                Position(
                    option_symbol=f"SPY{i}",
                    qty=1,
                    avg_price=1.0,
                    mark_price=1.5 if i < 6 else 0.7,
                    unrealized_pnl=0,
                    realized_pnl=50.0 if i < 6 else -30.0,
                    opened_at=now,
                    closed_at=now,
                    status="CLOSED",
                )
            )
        session.commit()

    gate = runtime.promotion_gate()
    assert "metrics" in gate
    assert gate["metrics"]["trade_count"] >= 10
