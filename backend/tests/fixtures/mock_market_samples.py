"""
Deterministic mock market samples for algorithm tests.

Each sample is documented so failures show which rule blocked or allowed a trade.
"""

from app.trading.types import OptionContract, SignalContext

# --- Signal contexts (strategy inputs) ---


def ctx_call_trend_volume_spike(symbol: str = 'SPX') -> SignalContext:
    """All CALL rules pass: price > VWAP, breaks prev high, MA5>MA10>MA20, volume > 1.2 * avg."""
    return SignalContext(
        symbol=symbol,
        price=5010.0,
        vwap=5005.0,
        prev_high=5008.0,
        prev_low=4995.0,
        ma5=5012.0,
        ma10=5008.0,
        ma20=5000.0,
        volume=2_400_000,
        avg_volume=1_000_000,
        day_high=5015.0,
        day_low=4980.0,
    )


def ctx_put_trend_volume_spike(symbol: str = 'SPX') -> SignalContext:
    """All PUT rules pass: price < VWAP, breaks prev low, MA5<MA10<MA20, volume > 1.2 * avg."""
    return SignalContext(
        symbol=symbol,
        price=4990.0,
        vwap=5005.0,
        prev_high=5010.0,
        prev_low=4995.0,
        ma5=4988.0,
        ma10=4995.0,
        ma20=5005.0,
        volume=2_400_000,
        avg_volume=1_000_000,
        day_high=5015.0,
        day_low=4980.0,
    )


def ctx_call_but_volume_not_expanding(symbol: str = 'SPX') -> SignalContext:
    """CALL geometry OK but volume <= 1.2 * avg — strategy should return None."""
    c = ctx_call_trend_volume_spike(symbol)
    return SignalContext(
        symbol=c.symbol,
        price=c.price,
        vwap=c.vwap,
        prev_high=c.prev_high,
        prev_low=c.prev_low,
        ma5=c.ma5,
        ma10=c.ma10,
        ma20=c.ma20,
        volume=1_000_000,
        avg_volume=1_000_000,
        day_high=c.day_high,
        day_low=c.day_low,
    )


def ctx_chop_no_clear_trend(symbol: str = 'SPX') -> SignalContext:
    """MAs not stacked; no CALL or PUT — expect None."""
    return SignalContext(
        symbol=symbol,
        price=5005.0,
        vwap=5005.0,
        prev_high=5010.0,
        prev_low=5000.0,
        ma5=5004.0,
        ma10=5006.0,
        ma20=5005.0,
        volume=2_000_000,
        avg_volume=1_000_000,
        day_high=5015.0,
        day_low=4995.0,
    )


# --- Option chains (contract selector inputs) ---


def chain_liquid_spx_calls_and_puts() -> list[OptionContract]:
    """Two tight-spread, liquid contracts; selector picks best CALL or PUT by side."""
    return [
        OptionContract(
            option_symbol='SPX-2026-01-10-5000-C',
            expiry='2026-01-10',
            strike=5000.0,
            right='C',
            delta=0.45,
            bid=10.0,
            ask=10.5,
            volume=500,
            open_interest=2000,
        ),
        OptionContract(
            option_symbol='SPX-2026-01-10-5010-C',
            expiry='2026-01-10',
            strike=5010.0,
            right='C',
            delta=0.40,
            bid=8.0,
            ask=9.5,
            volume=400,
            open_interest=1500,
        ),
        OptionContract(
            option_symbol='SPX-2026-01-10-4990-P',
            expiry='2026-01-10',
            strike=4990.0,
            right='P',
            delta=-0.48,
            bid=9.0,
            ask=9.8,
            volume=450,
            open_interest=1800,
        ),
    ]


def chain_only_wide_spread_calls() -> list[OptionContract]:
    """Spread > 10% — selector returns None for CALL side."""
    return [
        OptionContract(
            option_symbol='SPX-WIDE-C',
            expiry='2026-01-10',
            strike=5000.0,
            right='C',
            delta=0.45,
            bid=5.0,
            ask=8.0,
            volume=500,
            open_interest=2000,
        ),
    ]
