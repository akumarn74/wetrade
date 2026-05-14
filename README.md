# wetrade

Simulation-first options trading bot with hard risk gates.

**Product / SPX roadmap** (current capabilities vs phased plan: dynamic chain, goals, LLM boundaries): [docs/ROADMAP_SPX_AUTOTRADE.md](docs/ROADMAP_SPX_AUTOTRADE.md).

## Quick start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open dashboard at `http://127.0.0.1:8000/dashboard`.

## Production venv (recommended)

```bash
cd /Users/anathi/Documents/wetrade
source .venv-prod311/bin/activate
cd backend
uvicorn app.main:app --reload
```

## Core environment values

- `APP_MODE=SIM|WEBULL_PAPER|WEBULL_LIVE`
- `TRADE_SYMBOL=SPX` (or `SPY`)
- `OPTION_WATCHLIST` symbols must match the `TRADE_SYMBOL` prefix — refresh often; helper: `cd backend && python scripts/build_spx_watchlist.py --print-env-line` (see [DEPLOY.md](DEPLOY.md))
- `TRADING_ENABLED=false` by default
- Daily caps: `MAX_DAILY_LOSS`, `MAX_DAILY_PROFIT`, `MAX_TRADES_PER_DAY`
- **API hardening (any deploy beyond your laptop):** set `REQUIRE_API_KEY=true` and a long random `API_ADMIN_KEY`. Clients must send header `X-API-Key: <API_ADMIN_KEY>` on every `/api/*` route **except** `GET /api/health` (for load balancers). The dashboard has an optional field that stores the key in the browser session. For `curl`, add `-H 'X-API-Key: YOUR_KEY'`.

## Preflight checks

Before enabling trading:

```bash
curl http://127.0.0.1:8000/api/preflight
# With REQUIRE_API_KEY=true:
# curl -H 'X-API-Key: YOUR_KEY' http://127.0.0.1:8000/api/preflight
```

Only set `TRADING_ENABLED=true` once preflight returns `ready: true`.

## Algorithm scenario tests (mock data)

Deterministic samples live in `backend/tests/fixtures/mock_market_samples.py`.  
Integration-style tests in `backend/tests/test_algorithm_scenarios.py` run strategy → contract filter → full SIM signal cycle (with stub quotes) and document known gaps (e.g. trailing stop config not wired yet).

```bash
cd backend && source ../.venv-prod311/bin/activate
pytest tests/test_algorithm_scenarios.py -v
```

Objective-focused scenarios ($100/day cap, chop / low-confidence skips, emergency tick-drop exit):

```bash
pytest tests/test_objectives_scenarios.py -v
```

## Go-live (realtime, paper or live)

**Full deployment checklist** (keys, paper-then-live order, VPS hardening): [DEPLOY.md](DEPLOY.md) — section *When Webull API and Claude keys are ready*.  
Quick local check that `.env` is complete before starting `uvicorn`:

```bash
cd backend && source ../.venv-prod311/bin/activate
python scripts/check_env_ready.py
```

1. Use Python 3.11 venv and install deps (see **Production venv**).

2. Create `backend/.env` from `backend/.env.example` and set:
   - `APP_MODE=WEBULL_PAPER` first, then `WEBULL_LIVE` only after paper is stable
   - `WEBULL_*` and `OPTION_WATCHLIST` (must match `TRADE_SYMBOL` prefix)
   - `MAX_DAILY_LOSS`, `MAX_DAILY_PROFIT`, `MAX_TRADES_PER_DAY`

3. Start the API (keeps running for realtime loops):

```bash
cd /Users/anathi/Documents/wetrade/backend
source ../.venv-prod311/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. Preflight (must be `ready: true`):

```bash
curl -s http://127.0.0.1:8000/api/preflight | python3 -m json.tool
# If using API key auth, add to each curl below: -H 'X-API-Key: YOUR_KEY'
```

5. Enable trading and start the background runtime:

```bash
curl -s -X POST http://127.0.0.1:8000/api/trading-enabled \
  -H 'Content-Type: application/json' -d '{"enabled":true}'
curl -s -X POST http://127.0.0.1:8000/api/runtime \
  -H 'Content-Type: application/json' -d '{"running":true}'
```

6. Open the dashboard: `http://127.0.0.1:8000/dashboard`

Manual single-step debugging (optional):

```bash
curl -s -X POST http://127.0.0.1:8000/api/cycle/signal
curl -s -X POST http://127.0.0.1:8000/api/cycle/monitor
```

## Where to deploy for realtime trading

See [DEPLOY.md](DEPLOY.md) for VPS vs cloud VM, `systemd`, security (do not expose `/api` publicly without auth), and backups.
