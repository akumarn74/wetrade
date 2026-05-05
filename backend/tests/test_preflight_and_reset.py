from datetime import datetime, timedelta, timezone

from app import config as config_module
from app.config import Settings
from app.risk import manager as risk_module
from app.risk.manager import RiskManager
from app.runtime import engine as engine_module


def test_daily_reset_clears_risk_state(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    cfg = Settings()
    config_module.settings = cfg
    risk_module.settings = cfg

    rm = RiskManager()
    now = datetime.now(timezone.utc)
    rm.reset_for_new_day(now)
    rm.state.trades_today = 3
    rm.state.daily_realized_pnl = -100
    rm.state.consecutive_losses = 2

    changed = rm.reset_for_new_day(now + timedelta(days=1))
    assert changed is True
    assert rm.state.trades_today == 0
    assert rm.state.daily_realized_pnl == 0
    assert rm.state.consecutive_losses == 0


def test_preflight_returns_checks(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    cfg = Settings()
    config_module.settings = cfg
    engine_module.settings = cfg

    runtime = engine_module.TradingRuntime()
    data = runtime.preflight()
    assert 'ready' in data
    assert 'checks' in data
    assert 'mode' in data['checks']
