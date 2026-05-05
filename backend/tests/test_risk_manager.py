from datetime import datetime, timezone

from app import config as config_module
from app.config import Settings
from app.risk import manager as risk_module
from app.risk.manager import RiskManager


def test_daily_profit_halts_new_entries(monkeypatch):
    monkeypatch.setenv('MAX_DAILY_PROFIT', '100')
    monkeypatch.setenv('TRADING_ENABLED', 'true')
    cfg = Settings()
    config_module.settings = cfg
    risk_module.settings = cfg

    rm = RiskManager()
    rm.state.daily_realized_pnl = 120
    decision = rm.approve_entry(datetime.now(timezone.utc))
    assert decision.approved is False
    assert decision.reason == 'max_daily_profit_reached'


def test_trade_symbol_applied(monkeypatch):
    monkeypatch.setenv('TRADE_SYMBOL', 'SPX')
    from app.runtime import engine as engine_module

    cfg = Settings()
    config_module.settings = cfg
    engine_module.settings = cfg
    runtime = engine_module.TradingRuntime()
    assert runtime.symbol == 'SPX'
