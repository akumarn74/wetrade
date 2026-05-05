import pytest

from app.config import Settings
from app.runtime.engine import TradingRuntime
from app.storage.db import init_db


def test_runtime_uses_sim_broker_by_default(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    from app import config as config_module

    config_module.settings = Settings()
    from app.runtime import engine as engine_module

    engine_module.settings = config_module.settings
    init_db()
    runtime = TradingRuntime()
    assert runtime.account_snapshot()['mode'] == 'SIM'


def test_runtime_uses_webull_paper(monkeypatch):
    pytest.importorskip('webullsdkcore')
    monkeypatch.setenv('APP_MODE', 'WEBULL_PAPER')
    monkeypatch.setenv('WEBULL_APP_KEY', 'k')
    monkeypatch.setenv('WEBULL_APP_SECRET', 's')
    monkeypatch.setenv('WEBULL_ACCOUNT_ID', 'a')
    monkeypatch.setenv('OPTION_WATCHLIST', 'SPY250505C00520000')
    from app import config as config_module

    config_module.settings = Settings()
    from app.runtime import engine as engine_module
    from app.market_data import provider as provider_module

    engine_module.settings = config_module.settings
    provider_module.settings = config_module.settings
    runtime = TradingRuntime()
    assert runtime.account_snapshot()['mode'] == 'WEBULL_PAPER'


def test_invalid_mode_rejected(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'BAD_MODE')
    from app import config as config_module

    config_module.settings = Settings()
    with pytest.raises(RuntimeError):
        config_module.validate_startup_config()
