# Realtime trading: how it runs and where to deploy

## What “realtime” means here

The bot is a **long-running FastAPI process** that:

1. Polls Webull **market data** on a timer (`SIGNAL_LOOP_SECONDS`, `MONITOR_LOOP_SECONDS`).
2. Runs the strategy → risk gates → **limit orders** via Webull **Trading API**.
3. Persists state in **SQLite** (local file next to the app by default).

There is no separate “job runner” product: **you keep `uvicorn` (or gunicorn+uvicorn workers) running 24/5** on a machine that has stable outbound HTTPS to Webull and your API keys in environment variables.

Reference: [Webull OpenAPI overview](https://developer.webull.com/apis/docs/) (Trading API + Market Data API for your own account).

## Recommended deployment shape

| Environment | Use case |
|-------------|----------|
| **Your Mac / dev box** | Paper mode, debugging, dashboard. |
| **Small Linux VPS** | Always-on paper or live; static IP; easy `systemd`. |
| **Your home server / NUC** | Same as VPS if power and network are stable. |

**Avoid** serverless “one request then sleep” platforms for the core trading loop unless you redesign around external schedulers; you want a **persistent process**.

## Where to deploy (concrete options)

1. **VPS (most common)**  
   - Examples: AWS EC2, Google Compute Engine, DigitalOcean Droplet, Linode, Vultr, Hetzner.  
   - Pick a region close to you or with good latency to US markets if that matters for your style.

2. **Dedicated small VM in your cloud**  
   - Same as VPS, under your existing AWS/GCP/Azure account.

3. **Always-on container**  
   - ECS/Fargate, GKE small node pool, or a single Fly.io machine — still one long-lived task with env vars and a volume for SQLite (or switch DB later).

**Do not** expose the FastAPI control plane to the public internet without extra hardening. In plain terms:

1. **Bind-only** — run `uvicorn` with `--host 127.0.0.1` so nothing off the machine can open a TCP connection to the API. You then reach it via **SSH port forward**, **Tailscale**, or another VPN so only your devices see the host. This is “network security”: the API is not on the public internet at all.

2. **API key auth** — in `.env`, set `REQUIRE_API_KEY=true` and a long random `API_ADMIN_KEY`. Every client (dashboard, `curl`, scripts) must send `X-API-Key: <same value>` on all `/api/*` routes **except** `GET /api/health`. That stops accidental or malicious use if someone *can* reach the port (e.g. misconfigured firewall). Use bind-only **and** API keys when the process listens beyond localhost.

Also valid: **nginx + TLS** in front, or **VPN-only** subnet with bind on private interface — same idea: do not leave unauthenticated trading controls on `0.0.0.0:8000` facing the world.

## Python version

- **Mac dev:** Python **3.11** (or 3.12 for non-Webull work) matches `.venv-prod311`. Python **3.13** is blocked for Webull modes in `validate_startup_config()`.
- **Linux VPS + Webull:** the official Webull OpenAPI SDK pins **`grpcio==1.51.1`**, which has reliable **manylinux wheels for Python 3.10 / 3.11**. On **Python 3.12**, `pip` usually **compiles gRPC from source** (slow and often fails on small droplets). Use **`python3.10 -m venv .venv-prod311`** on the server, then run `bash backend/scripts/install_deps_droplet.sh` (that script refuses 3.12+ to avoid a 10+ minute dead-end).

## Production process (systemd sketch)

On Ubuntu after cloning the repo and creating `.venv-prod311`:

```ini
[Unit]
Description=wetrade trading API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/wetrade/backend
EnvironmentFile=/home/ubuntu/wetrade/backend/.env
ExecStart=/home/ubuntu/wetrade/.venv-prod311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust paths and user. Run `systemctl daemon-reload && systemctl enable --now wetrade`.

## Single worker

Use **one trading process** (one uvicorn worker) so in-memory risk state and broker session behavior stay consistent. If you scale horizontally later, move risk counters and kill-switch to shared storage (Redis/DB).

## Data and backups

- Default DB: `DATABASE_URL=sqlite:///./wetrade.db` under `backend/`.  
- Back up that file if you care about audit logs and PnL history.

## Monitoring

- Health: `GET /api/health`  
- Readiness before enabling orders: `GET /api/preflight`  
- Dashboard: `/dashboard` (static UI calling `/api/*`)

## Go-live sequence

See [README.md](README.md) **Go-live (realtime)** section for copy-paste `curl` commands.

## Checklist: when Webull API and Claude keys are ready

Use this order so you **paper trade first**, then switch to live only deliberately.

### 1. Machine prep (once per host)

- [ ] **Python 3.11** (or 3.12) venv with dependencies installed (`requirements.txt`; Webull SDK install notes in [README.md](README.md) if needed).
- [ ] Repo cloned; working copy on the machine that will run `uvicorn` continuously.
- [ ] `backend/.env` created from `.env.example` — **never commit `.env`** or paste keys into chat logs.

### 2. Fill secrets (when you receive them)

| Variable | When you need it |
|----------|-------------------|
| `WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, `WEBULL_ACCOUNT_ID` | Any `WEBULL_PAPER` / `WEBULL_LIVE` run |
| `OPTION_WATCHLIST` | Comma-separated symbols **from Webull**; each must start with `TRADE_SYMBOL` (e.g. `SPX` + `SPX…`) — see **Refreshing OPTION_WATCHLIST** below |
| `CLAUDE_API_KEY` | Recommended if `MIN_ENTRY_CONFIDENCE` > 0 (default 0.55 in `.env.example`) |
| `API_ADMIN_KEY` | Required if `REQUIRE_API_KEY=true` (recommended on any VPS) |

### Refreshing OPTION_WATCHLIST (required for realistic paper)

The bot **does not** download the full option chain. It only requests snapshots for **exact tickers** in `OPTION_WATCHLIST`. Stale strikes (e.g. from when SPX was far from today’s level) produce useless quotes or **`no_valid_contract`** even when the bar strategy fires.

**Automated helper (queries Webull, filters live quotes)**

From `backend/` with the same `.env` as `uvicorn` (needs Webull keys; `OPTION_WATCHLIST` may be empty):

```bash
source ../.venv-prod311/bin/activate   # or your venv
# Default: expiry = today (US/Eastern), spot = last SPY close (proxy for SPX)
python scripts/build_spx_watchlist.py --print-env-line

# Pin spot if you want to center strikes around a level (e.g. SPX ~7500)
python scripts/build_spx_watchlist.py --spot 7500 --print-env-line

# Explicit 0DTE / weekly expiry
python scripts/build_spx_watchlist.py --expiry 2026-05-12 --spot 7500 --print-env-line
```

Copy the printed `OPTION_WATCHLIST=...` line into `backend/.env` and **restart `uvicorn`**. If nothing passes filters, try `--strikes-each-side 6` or a different `--expiry`. If Webull uses a different strike encoding for your account, use `--strike-field-scale` (default `100` matches `SPX250106C00600000` in `.env.example`).

**When to refresh**

- **0DTE / intraday SPX:** at least **once per session morning**, and again if spot moves enough that your listed strikes are no longer near the money you want.
- **Weekly / fixed lists:** whenever expiry rolls or you change strategy strikes.

**What to list**

1. In Webull (app or portal), open the **SPX** chain for the **expiry you trade** (often same-day for 0DTE tests).
2. Copy **4–12** option symbols **Webull uses for OpenAPI `US_OPTION`** (same strings as in their chain / docs). Include **both calls and puts** if you want either direction to be selectable after a signal.
3. Center strikes **around current SPX** (e.g. a few strikes above and below spot), not a short list left over from an old level.
4. Put them in `backend/.env` as **comma-separated** values, no spaces unless your tooling strips them:

   ```env
   OPTION_WATCHLIST=SPX...,SPX...,SPX...
   ```

5. **Restart `uvicorn`** so settings reload (env is read at process start).

After a signal, `ContractSelector` still filters by **delta band, volume, open interest, and bid/ask spread** (`backend/app/trading/contracts.py`). If everything is filtered out, widen the watchlist **or** relax those rules in code once you understand live liquidity.

Start with:

```env
APP_MODE=WEBULL_PAPER
TRADING_ENABLED=false
```

### 3. Validate before starting the process

From `backend/`:

```bash
source ../.venv-prod311/bin/activate   # or your venv
python scripts/check_env_ready.py
```

Fix anything it reports, then start `uvicorn` (see README **Go-live** and the **systemd** unit above).

### 4. Runtime sequence (every session)

1. `GET /api/preflight` — all checks should show `ready: true` before you arm the bot.
2. Use the dashboard or `curl` to set `TRADING_ENABLED` and runtime **only** after preflight is green.
3. Watch logs, `/api/events`, and broker UI during **paper** sessions.
4. **Live:** change only `APP_MODE=WEBULL_LIVE` (and confirm Webull’s live API terms) after paper is stable — keep the same risk caps until you intentionally change them.

### 5. Production hardening (VPS / cloud)

- [ ] `uvicorn` bound to `127.0.0.1` (or private interface) + SSH tunnel / Tailscale / VPN for access.
- [ ] `REQUIRE_API_KEY=true` and a long random `API_ADMIN_KEY`; dashboard or `curl` sends `X-API-Key`.
- [ ] Back up `wetrade.db` if you care about history (see **Data and backups** above).
