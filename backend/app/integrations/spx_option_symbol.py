"""Encode/decode Webull-style compact SPX option tickers (see .env.example)."""

from __future__ import annotations

import re
from datetime import date


_SPX_OSi = re.compile(
    r"^(?P<root>SPXW|SPX)(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike8>\d{8})$",
    re.IGNORECASE,
)

_VALID_ROOTS = frozenset({"SPX", "SPXW"})


def encode_spx_option_ticker(
    expiry: date,
    strike: int,
    right: str,
    *,
    root: str = "SPX",
    strike_field_scale: int = 100,
) -> str:
    """root + YYMMDD + C|P + zero-padded int(strike * strike_field_scale) (default scale 100)."""
    r = root.strip().upper()
    if r not in _VALID_ROOTS:
        raise ValueError(f"root must be one of {sorted(_VALID_ROOTS)}, got {root!r}")
    suf = f"{int(round(strike * strike_field_scale)):08d}"
    return f"{r}{expiry.strftime('%y%m%d')}{right.upper()}{suf}"


def decode_spx_option_ticker(ticker: str, *, strike_field_scale: int = 100) -> tuple[date, float, str, str]:
    """
    Returns (expiry, strike, 'C'|'P', underlying_root).

    underlying_root is the ticker prefix (SPX or SPXW) — pass to Webull Trade /trade/security as `symbol`.
    Strike = int(strike_field) / strike_field_scale (default scale 100).
    """
    m = _SPX_OSi.match(ticker.strip().upper())
    if not m:
        raise ValueError(f"Not a supported SPX compact option ticker: {ticker!r}")
    yy, mm, dd = int(m.group("yy")), int(m.group("mm")), int(m.group("dd"))
    year = 2000 + yy if yy < 70 else 1900 + yy
    exp = date(year, mm, dd)
    scale = float(strike_field_scale) if strike_field_scale else 100.0
    strike = int(m.group("strike8")) / scale
    cp = m.group("cp").upper()
    root = m.group("root").upper()
    if cp not in ("C", "P"):
        raise ValueError(f"Invalid put/call in ticker: {ticker!r}")
    return exp, strike, cp, root
