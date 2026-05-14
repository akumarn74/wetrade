# SPX day-trading roadmap: auto trade, $100/day framing, and evolution from today’s code

This document captures the **architectural plan** for growing WeTrade toward **automated SPX options** day trading, how to treat the **current implementation**, and what is **realistic to achieve**.

It is **not** a promise of profitability. Options on indices are high variance; engineering can deliver **process, limits, and measurement**, not a daily paycheck.

---

## 1. Goal: “$100 / day”

Treat **`MAX_DAILY_PROFIT` ≈ $100** as a **daily take-profit / harvest ceiling** (stop trading once reached), paired with a **`MAX_DAILY_LOSS`** you can survive repeatedly.

- **Do not** treat $100 as “the bot must earn this every session.” Some days will be **red**, **flat**, or **below** target even if the system behaves well.
- **Do** use the existing caps so one bad day or one bug does not dominate the account.

---

## 2. What the current implementation is

| Layer | Behavior |
|--------|-----------|
| **Market data (Webull)** | 5m **context** for `TRADE_SYMBOL`: **SPX** uses **SPY** bars under **`US_ETF`**; production host **`api.webull.com`** (hostname-only for signing). |
| **Option quotes** | **Only** symbols listed in **`OPTION_WATCHLIST`** are snapshotted (`US_OPTION`). There is **no** full-chain fetch. |
| **Signal (direction)** | **`StrategyEngine`**: strict rule set (VWAP, prior high/low, MA order, volume vs 20-bar average). **Most** cycles → **no signal** (by design). |
| **Claude** | Runs **after** a rule signal: **`confidence`**, **`chop_warning`**, etc. Can **block** entries; does **not** pick strikes or build the option universe. |
| **Contract choice** | **`ContractSelector`**: filters watchlist snapshots by **delta band**, **volume**, **OI**, **spread**. |
| **Risk** | Daily caps, consecutive losses, **session window** (`MARKET_OPEN_TIME` / `MARKET_CLOSE_TIME`, first/last minutes). **Note:** window math today uses **UTC wall clock** unless you align server TZ or fix code to US/Eastern. |
| **Execution** | **`WebullBroker`**: real SDK **option limit** orders + status polling for fills; monitor loop handles **exits** (stop / take-profit / emergency tick drop). |
| **Runtime** | FastAPI + background loop when **`runtime.running`**; **`TRADING_ENABLED`** master switch. |

References: `backend/app/runtime/engine.py`, `backend/app/trading/strategy.py`, `backend/app/trading/contracts.py`, `backend/app/market_data/provider.py`, `DEPLOY.md` (watchlist refresh).

---

## 3. What we can achieve **with the current stack**

**Achievable now (paper first, then small live):**

- **End-to-end plumbing**: Webull auth, bars, snapshots, orders, SQLite audit trail, dashboard / `curl` control.
- **Discipline**: hard **daily** loss/profit stops, max trades, order timeout, exit automation for open positions.
- **Rare but testable entries**: when rules + liquidity filters align, **real** paper orders through Webull.
- **Operational learning**: logs, `/api/events`, slippage, how often **`no_signal`** vs **`no_valid_contract`** vs **`outside_trade_window`** occur.

**Hard to achieve without changes:**

- **Day-to-day realism near SPX spot** with a **static** watchlist (strikes go stale fast, especially **0DTE**).
- **High trade frequency** with the current **very strict** rule engine.
- **“Claude picks the option”** — not implemented; Claude only **scores / vetoes** after rules fire.

---

## 4. What to do **with** the current implementation

**Keep it.** It is the **correct foundation**: broker adapter, risk shell, persistence, preflight, deploy path.

**Use it deliberately:**

1. **Paper (`WEBULL_PAPER`)** until chain automation exists and metrics look sane.
2. **Refresh `OPTION_WATCHLIST` manually** every session (see `DEPLOY.md` → *Refreshing OPTION_WATCHLIST*) until dynamic universe ships.
3. **Fix session time semantics** (US Eastern for SPX session) so “first/last minutes” and “market open” match reality on the server.
4. **Measure** before changing the goal: distribution of outcomes, block reasons, fill quality.

**Do not** throw away the rule + risk core to chase LLM-driven symbol picking; **extend** around it.

---

## 5. Target architecture (phased)

### Phase A — **Dynamic option universe** (highest leverage)

- **Interim tool (now):** `backend/scripts/build_spx_watchlist.py` — uses live **`US_OPTION` snapshots** to validate generated SPX tickers near spot (default spot = last **SPY** close as SPX proxy; default expiry = **today US/Eastern**). Run from `backend/`; see [DEPLOY.md](../DEPLOY.md) (*Refreshing OPTION_WATCHLIST*).
- **In-app (later):** fetch **SPX option chain / instruments** from Webull (per official Data / Trading docs) for chosen **expiry** (e.g. 0DTE), cache (e.g. 30–120s) for **rate limits**, and wire into `option_chain()` so `OPTION_WATCHLIST` is optional.
- Keep **`OPTION_WATCHLIST` as override** when set (debug / fallback).

**Outcome:** same strategy + selector, but inputs **track the market**.

### Phase B — **Execution and session hardening**

- **Flatten-before-close** for 0DTE (explicit rule).
- Limit price logic (mid ± fraction of spread, bounded).
- Optional **paper-vs-live** feature flags and stricter logging for live.

### Phase C — **LLM (optional, bounded)**

- Input: **shortlist only** (e.g. 5–15 contracts JSON from Webull).
- Output: **strict schema** (`veto`, `rank`, or `confidence_by_id`) with **server-side validation** (symbol must be in shortlist).
- **Never** free-form symbol generation.

**Outcome:** advisory layer on **ranked human-auditable candidates**, not open-ended chain search.

### Phase D — **Strategy / regime**

- Either **tune** the existing rule book with data **or** add a **regime filter** (trend vs chop) with tests.
- Backtest or replay **before** scaling size toward any dollar target.

---

## 6. Honest “what we can achieve” summary

| Expectation | Realistic? |
|-------------|-------------|
| Reliable **automation** (submit, track, exit with caps) | **Yes**, with current direction + ops discipline. |
| **$100 every day** | **No guarantee**; variance and regime dominate. |
| **$100 as “good day” cap** with controlled downside | **Yes**, as a **risk design**, not expected daily PnL. |
| **Dynamic SPX options without manual watchlist** | **Yes**, after Phase A (new code + tests). |
| **Fully autonomous “agent picks any strike”** | **Not recommended** as v1; high error cost; use shortlist + validators if at all. |

---

## 7. Suggested next engineering tickets (order)

1. **US/Eastern session correctness** in `RiskManager` (or droplet `TZ=America/New_York` + documented semantics).
2. **Webull chain → candidate builder** + wire into `WebullMarketDataProvider.option_chain()` (or parallel path).
3. **Metrics endpoint or nightly summary**: counts of `no_signal`, `no_valid_contract`, `denied:*`, fills, fees.
4. **0DTE flatten rule** before `MARKET_CLOSE_TIME` minus buffer.
5. Revisit **`ContractSelector`** thresholds once real chain data flows (they were tuned for a tiny watchlist).

---

## 8. Related docs

- [DEPLOY.md](../DEPLOY.md) — deployment, security, **refreshing `OPTION_WATCHLIST`**
- [README.md](../README.md) — quick start, preflight, go-live `curl` flow
- `backend/.env.example` — environment variables

---

*Last updated: aligns product intent (SPX auto day-trade, ~$100/day framing) with current codebase capabilities and a phased evolution plan.*
