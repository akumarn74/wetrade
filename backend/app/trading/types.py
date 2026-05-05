from dataclasses import dataclass
from datetime import datetime


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OptionContract:
    option_symbol: str
    expiry: str
    strike: float
    right: str
    delta: float
    bid: float
    ask: float
    volume: int
    open_interest: int

    @property
    def spread_pct(self) -> float:
        mid = (self.bid + self.ask) / 2 if (self.bid + self.ask) else 0
        return 1.0 if mid == 0 else (self.ask - self.bid) / mid


@dataclass
class SignalContext:
    symbol: str
    price: float
    vwap: float
    prev_high: float
    prev_low: float
    ma5: float
    ma10: float
    ma20: float
    volume: float
    avg_volume: float
    day_high: float
    day_low: float


@dataclass
class TradeSignal:
    side: str
    reason: str
    confidence: float = 0.0
