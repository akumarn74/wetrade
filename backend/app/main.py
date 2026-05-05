import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings, validate_startup_config
from app.runtime.engine import runtime
from app.storage.db import init_db

app = FastAPI(title='WeTrade Options API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(router)
app.mount('/dashboard', StaticFiles(directory='../dashboard', html=True), name='dashboard')


async def loop_worker():
    while True:
        if runtime.running:
            await runtime.run_signal_cycle()
            runtime.run_monitor_cycle()
        await asyncio.sleep(min(settings.signal_loop_seconds, settings.monitor_loop_seconds))


@app.on_event('startup')
async def startup():
    validate_startup_config()
    init_db()
    asyncio.create_task(loop_worker())
