"""Encode/decode Webull-style compact SPX option tickers (see .env.example)."""

from __future__ import annotations

import re
from datetime import date


_SPX_OSi = re.compile(
    r"^SPX(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike8>\d{8})$",
    re.IGNORECASE,
)


def encode_spx_option_ticker(expiry: date, strike: int, right: str, *, strike_field_scale: int = 100) -> str:
    """SPX + YYMMDD + C|P + zero-padded int(strike * strike_field_scale) (default scale 100)."""
    suf = f"{int(round(strike * strike_field_scale)):08d}"
    return f"SPX{expiry.strftime('%y%m%d')}{right.upper()}{suf}"


def decode_spx_option_ticker(ticker: str) -> tuple[date, float, str]:
    """
    Returns (expiry, strike, 'C'|'P').
    Strike = int(strike_field) / 100 when strike_field_scale is 100 (matches encode default).
    """
    m = _SPX_OSi.match(ticker.strip().upper())
    if not m:
        raise ValueError(f"Not a supported SPX compact option ticker: {ticker!r}")
    yy, mm, dd = int(m.group("yy")), int(m.group("mm")), int(m.group("dd"))
    year = 2000 + yy if yy < 70 else 1900 + yy
    exp = date(year, mm, dd)
    strike = int(m.group("strike8")) / 100.0
    cp = m.group("cp").upper()
    if cp not in ("C", "P"):
        raise ValueError(f"Invalid put/call in ticker: {ticker!r}")
    return exp, strike, cp
