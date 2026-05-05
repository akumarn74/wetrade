from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import select

from app.api.deps import require_admin_api_key
from app.api.schemas import RuntimeRequest, ToggleRequest
from app.config import settings
from app.runtime.engine import runtime
from app.storage.db import get_session
from app.storage.models import AgentEvent, Order, Position

router = APIRouter(prefix='/api')
_protected = [Depends(require_admin_api_key)]


@router.get('/health')
def health():
    """Public: use for load balancers / uptime checks (no secrets)."""
    return {'status': 'ok', 'mode': settings.app_mode, 'trading_enabled': settings.trading_enabled, 'ts': datetime.now(timezone.utc)}


@router.get('/mode', dependencies=_protected)
def mode():
    return {'mode': settings.app_mode}


@router.post('/trading-enabled', dependencies=_protected)
def trading_enabled(payload: ToggleRequest):
    settings.trading_enabled = payload.enabled
    return {'trading_enabled': settings.trading_enabled}


@router.post('/runtime', dependencies=_protected)
def set_runtime(payload: RuntimeRequest):
    runtime.running = payload.running
    return {'running': runtime.running}


@router.get('/risk', dependencies=_protected)
def risk_status():
    return runtime.risk.state.__dict__

@router.get('/account', dependencies=_protected)
def account():
    return runtime.account_snapshot()


@router.get('/positions', dependencies=_protected)
def positions():
    with get_session() as session:
        data = session.exec(select(Position).order_by(Position.id.desc())).all()
        return data


@router.get('/orders', dependencies=_protected)
def orders():
    with get_session() as session:
        data = session.exec(select(Order).order_by(Order.id.desc())).all()
        return data


@router.get('/events', dependencies=_protected)
def events():
    with get_session() as session:
        data = session.exec(select(AgentEvent).order_by(AgentEvent.id.desc()).limit(50)).all()
        return data

@router.get('/trades', dependencies=_protected)
def trades():
    return runtime.recent_trades()

@router.get('/promotion-gate', dependencies=_protected)
def promotion_gate():
    return runtime.promotion_gate()

@router.get('/preflight', dependencies=_protected)
def preflight():
    return runtime.preflight()


@router.post('/cycle/signal', dependencies=_protected)
async def signal_cycle():
    await runtime.run_signal_cycle()
    return {'ok': True}


@router.post('/cycle/monitor', dependencies=_protected)
def monitor_cycle():
    runtime.run_monitor_cycle()
    return {'ok': True}
