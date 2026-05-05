import pytest
from fastapi.testclient import TestClient

from app import config as config_module
from app.api import deps
from app.config import Settings, validate_startup_config


@pytest.fixture
def sim_settings(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    cfg = Settings()
    config_module.settings = cfg
    deps.settings = cfg
    return cfg


def test_health_public_when_api_key_required(sim_settings):
    sim_settings.require_api_key = True
    sim_settings.api_admin_key = 'test-secret-key'
    from app.main import app

    with TestClient(app) as client:
        r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'


def test_protected_route_401_without_key(sim_settings):
    sim_settings.require_api_key = True
    sim_settings.api_admin_key = 'test-secret-key'
    from app.main import app

    with TestClient(app) as client:
        r = client.get('/api/risk')
    assert r.status_code == 401


def test_protected_route_200_with_valid_key(sim_settings):
    sim_settings.require_api_key = True
    sim_settings.api_admin_key = 'test-secret-key'
    from app.main import app

    with TestClient(app) as client:
        r = client.get('/api/risk', headers={'X-API-Key': 'test-secret-key'})
    assert r.status_code == 200
    body = r.json()
    assert 'trades_today' in body


def test_validate_startup_rejects_require_key_without_admin(sim_settings):
    sim_settings.require_api_key = True
    sim_settings.api_admin_key = ''
    with pytest.raises(RuntimeError, match='API_ADMIN_KEY'):
        validate_startup_config()


def test_app_startup_fails_when_require_key_without_admin(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'SIM')
    cfg = Settings()
    cfg.require_api_key = True
    cfg.api_admin_key = ''
    config_module.settings = cfg
    deps.settings = cfg
    from app.main import app

    with pytest.raises(RuntimeError, match='API_ADMIN_KEY'):
        with TestClient(app):
            pass
