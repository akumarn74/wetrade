#!/usr/bin/env python3
"""
Build OPTION_WATCHLIST from live Webull market data (US_OPTION snapshots).

Uses SPY's last trade as a spot proxy for SPX (same as the app's bar path), generates
near-ATM SPX option tickers for a chosen expiry, then keeps only symbols that return
usable snapshot rows (bid/ask + greeks when present).

Run from the backend directory (loads backend/.env):

  cd backend && source ../.venv-prod311/bin/activate
  python scripts/build_spx_watchlist.py
  python scripts/build_spx_watchlist.py --spot 7525 --expiry 2026-05-12 --strikes-each-side 4
  python scripts/build_spx_watchlist.py --print-env-line | tee /tmp/watchlist.txt

Requires WEBULL_APP_KEY, WEBULL_APP_SECRET, WEBULL_REGION_ID, WEBULL_OPENAPI_DOMAIN in .env
(same as the running app). OPTION_WATCHLIST may be empty for this script.

Ticker shape matches Webull-style compact strings (see .env.example):
  SPX + YYMMDD + C|P + 8-digit strike field = int(round(strike * 100))
  Example: SPX250106C00600000 -> strike 6000 (6000*100 = 600000 -> zero-padded to 8 -> 00600000)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _spot_from_spy(api) -> float:
    r = api.market_data.get_history_bar("SPY", category="US_ETF", timespan="M1", count="2")
    data = r.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError("Could not read SPY M1 bars for spot proxy")
    last = data[-1]
    close = float(last.get("close") or last.get("c") or 0.0)
    if close <= 0:
        raise RuntimeError("SPY last close invalid")
    return close


def _round_spot_step(x: float, step: int) -> int:
    return int(round(x / step) * step)


def _encode_spx_ticker(expiry: date, strike: int, right: str, *, strike_field_scale: int) -> str:
    suf = f"{int(round(strike * strike_field_scale)):08d}"
    return f"SPX{expiry.strftime('%y%m%d')}{right.upper()}{suf}"


def _snapshot_rows(api, symbols: list[str]) -> list[dict[str, Any]]:
    if not symbols:
        return []
    joined = ",".join(symbols)
    resp = api.market_data.get_snapshot(joined, category="US_OPTION")
    body = resp.json()
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        return [body]
    return []


def _mid(row: dict[str, Any]) -> float:
    bid = float(row.get("bid_price") or row.get("bid") or 0.0)
    ask = float(row.get("ask_price") or row.get("ask") or 0.0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return float(row.get("close") or row.get("last_price") or 0.0)


def _delta(row: dict[str, Any]) -> float | None:
    for k in ("delta", "greeks_delta"):
        v = row.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OPTION_WATCHLIST via Webull US_OPTION snapshots")
    parser.add_argument("--spot", type=float, default=None, help="Override index spot (default: last SPY close as proxy)")
    parser.add_argument("--expiry", type=str, default=None, help="Expiration YYYY-MM-DD (default: today US/Eastern)")
    parser.add_argument("--strike-step", type=int, default=5, help="Strike spacing (SPX index points)")
    parser.add_argument("--strikes-each-side", type=int, default=4, help="How many strikes above/below ATM to try")
    parser.add_argument("--max-output", type=int, default=12, help="Max symbols in final watchlist")
    parser.add_argument(
        "--strike-field-scale",
        type=int,
        default=100,
        help="Strike encoded as int(strike*scale) zero-padded to 8 digits (100 matches .env.example)",
    )
    parser.add_argument("--print-env-line", action="store_true", help="Print OPTION_WATCHLIST=... for .env paste")
    args = parser.parse_args()

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        print("Python 3.9+ with zoneinfo required", file=sys.stderr)
        return 2

    try:
        from app.integrations.webull_client import WebullAPIClient
    except Exception as exc:  # pragma: no cover
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    api = WebullAPIClient().api

    if args.expiry:
        expiry = date.fromisoformat(args.expiry)
    else:
        expiry = datetime.now(ZoneInfo("America/New_York")).date()

    spot = args.spot if args.spot is not None else _spot_from_spy(api)
    atm = _round_spot_step(spot, args.strike_step)
    strikes: list[int] = []
    for k in range(-args.strikes_each_side, args.strikes_each_side + 1):
        strikes.append(atm + k * args.strike_step)

    candidates: list[str] = []
    for strike in strikes:
        for right in ("C", "P"):
            candidates.append(_encode_spx_ticker(expiry, strike, right, strike_field_scale=args.strike_field_scale))

    # Snapshot in chunks (Webull documents batch limits; stay conservative)
    chunk = 20
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    for i in range(0, len(candidates), chunk):
        part = candidates[i : i + chunk]
        try:
            rows = _snapshot_rows(api, part)
        except Exception as exc:
            print(f"snapshot error for chunk starting {part[0]}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            sym = str(row.get("symbol") or "").strip()
            if sym:
                rows_by_symbol[sym] = row

    usable: list[tuple[float, str, dict[str, Any]]] = []
    for sym, row in rows_by_symbol.items():
        mid = _mid(row)
        if mid <= 0:
            continue
        bid = float(row.get("bid_price") or row.get("bid") or 0.0)
        ask = float(row.get("ask_price") or row.get("ask") or 0.0)
        if bid <= 0 or ask <= 0:
            continue
        spread = (ask - bid) / mid if mid else 1.0
        if spread > 0.25:
            continue
        d = _delta(row)
        if d is None:
            continue
        ad = abs(d)
        if not (0.30 <= ad <= 0.60):
            continue
        usable.append((spread, sym, row))

    usable.sort(key=lambda x: (x[0], abs((_delta(x[2]) or 0) - 0.45)))
    picked = [u[1] for u in usable[: args.max_output]]

    if not picked:
        print(
            "No symbols passed filters (bid/ask, spread<=25%, delta in [0.30,0.60]).\n"
            "Try: different --expiry (0DTE must match today's SPX listing), wider --strikes-each-side,\n"
            "or pass --spot explicitly. If Webull rejects tickers, verify OSI format in the app chain.",
            file=sys.stderr,
        )
        # Still print attempted sample for debugging
        print("# Attempted (first 6): " + ",".join(candidates[:6]), file=sys.stderr)
        return 1

    line = ",".join(picked)
    if args.print_env_line:
        print(f"OPTION_WATCHLIST={line}")
    else:
        print(json.dumps({"spot_proxy": spot, "atm_strike": atm, "expiry": str(expiry), "symbols": picked}, indent=2))
        print()
        print("Paste into backend/.env:")
        print(f"OPTION_WATCHLIST={line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
