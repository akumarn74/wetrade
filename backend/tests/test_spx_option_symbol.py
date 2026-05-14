from datetime import date

from app.integrations.spx_option_symbol import decode_spx_option_ticker, encode_spx_option_ticker


def test_encode_decode_roundtrip():
    exp = date(2025, 1, 6)
    t = encode_spx_option_ticker(exp, 6000, "C", strike_field_scale=100)
    assert t == "SPX250106C00600000"
    e2, k2, r2 = decode_spx_option_ticker(t)
    assert e2 == exp
    assert k2 == 6000.0
    assert r2 == "C"


def test_encode_7480_strike():
    exp = date(2026, 5, 14)
    t = encode_spx_option_ticker(exp, 7480, "P", strike_field_scale=100)
    assert t.endswith("00748000")
    e2, k2, r2 = decode_spx_option_ticker(t)
    assert k2 == 7480.0
    assert r2 == "P"
