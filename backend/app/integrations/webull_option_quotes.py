"""
Option quotes for US index options via Webull Trade API.

HTTP market-data snapshot (`/market-data/snapshot`) only supports US_STOCK / US_ETF;
`US_OPTION` returns UNSUPPORTED_CATEGORY on production. We use `GET /trade/security`
(`trade_instrument.get_trade_security_detail`) per contract instead.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.integrations.spx_option_symbol import decode_spx_option_ticker

try:
    from webullsdkcore.exception.exceptions import ServerException
except ImportError:  # pragma: no cover
    ServerException = Exception  # type: ignore[misc, assignment]


def _f(d: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = d.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


def _i(d: dict[str, Any], *keys: str, default: int = 0) -> int:
    for k in keys:
        v = d.get(k)
        if v is None or v == "":
            continue
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    return default


def trade_security_json_to_chain_row(raw: dict[str, Any], fallback_osi: str) -> dict[str, Any]:
    """Map trade/security (or similar) JSON into the shape `WebullMarketDataProvider` expects."""
    sym = str(raw.get("symbol") or raw.get("ticker") or raw.get("option_symbol") or fallback_osi)
    bid = _f(raw, "bid_price", "bid", "bidPrice", "buyPrice")
    ask = _f(raw, "ask_price", "ask", "askPrice", "sellPrice")
    delta = raw.get("delta")
    if delta is None:
        delta = raw.get("greeks_delta") or raw.get("delta_value")
    opt_type = str(raw.get("option_type") or raw.get("right") or "")
    return {
        "symbol": sym,
        "bid_price": bid,
        "ask_price": ask,
        "bid": bid,
        "ask": ask,
        "delta": float(delta) if delta is not None and str(delta) != "" else None,
        "greeks_delta": raw.get("greeks_delta"),
        "option_type": opt_type,
        "expiration_date": str(raw.get("expiration_date") or raw.get("option_expire_date") or raw.get("init_exp_date") or ""),
        "strike_price": _f(raw, "strike_price", "strike", "strikePrice"),
        "volume": _i(raw, "volume", "vol"),
        "open_interest": _i(raw, "open_interest", "openInterest", "oi"),
        "close": _f(raw, "close", "last_price", "lastPrice", "price"),
        "last_price": _f(raw, "last_price", "lastPrice", "price"),
    }


def _strike_query_param(strike: float) -> str:
    if abs(strike - round(strike)) < 1e-6:
        return str(int(round(strike)))
    return f"{strike:.2f}"


def _trade_security_detail_response(
    api: Any,
    underlying: str,
    exp_iso: str,
    strike_str: str,
    inst: str,
    *,
    account_id: str | None,
) -> Any:
    """
    Build the same GET /trade/security as `TradeInstrument.get_trade_security_detail`, but set
    `account_id` when provided (the stock SDK method omits it; some environments return 404 without it).
    """
    from webullsdktrade.request.get_trade_security_detail_request import TradeSecurityDetailRequest

    req = TradeSecurityDetailRequest()
    req.set_symbol(underlying)
    req.set_market("US")
    req.set_instrument_super_type("OPTION")
    req.set_instrument_type(inst)
    req.set_strike_price(strike_str)
    req.set_init_exp_date(exp_iso)
    aid = (account_id or "").strip()
    if aid:
        req.set_account_id(aid)
    return api.trade_instrument.client.get_response(req)


def fetch_option_rows_trade_security(
    api: Any,
    option_symbols: list[str],
    *,
    account_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    :param api: `webullsdktrade.api.API` instance (same as `WebullAPIClient().api`).
    :param option_symbols: Compact tickers parseable by `decode_spx_option_ticker` (SPX… or SPXW…).
    :param account_id: Webull account id; defaults to ``settings.webull_account_id`` when omitted.
    :returns: (rows, per-symbol error strings for failures).
    """
    aid = account_id if account_id is not None else (settings.webull_account_id or "").strip() or None
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for osi in option_symbols:
        osi = osi.strip()
        if not osi:
            continue
        try:
            exp, strike, cp, underlying = decode_spx_option_ticker(osi)
        except ValueError:
            continue
        inst = "CALL_OPTION" if cp == "C" else "PUT_OPTION"
        exp_iso = exp.isoformat()
        strike_str = _strike_query_param(strike)
        try:
            resp = _trade_security_detail_response(
                api,
                underlying,
                exp_iso,
                strike_str,
                inst,
                account_id=aid,
            )
        except ServerException as exc:  # type: ignore[misc]
            errors.append(f"{osi}: HTTP Status: {getattr(exc, 'http_status', '?')}, {exc}")
            continue
        try:
            raw = resp.json()
        except (ValueError, AttributeError, json.JSONDecodeError):
            errors.append(f"{osi}: invalid JSON in trade/security response")
            continue
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            raw = raw["data"]
        if not isinstance(raw, dict):
            errors.append(f"{osi}: unexpected trade/security payload type")
            continue
        rows.append(trade_security_json_to_chain_row(raw, osi))
    return rows, errors
