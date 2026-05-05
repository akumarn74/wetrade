from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class MarketSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    timestamp: datetime
    price: float
    vwap: float
    ma5: float
    ma10: float
    ma20: float
    volume: float
    day_high: float
    day_low: float


class Signal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    symbol: str
    side: str
    reason: str
    confidence: float = 0.0


class OrderIntent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    symbol: str
    option_symbol: str
    side: str
    qty: int
    limit_price: float
    status: str


class RiskDecision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    approved: bool
    reason: str
    signal_id: Optional[int] = None


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    broker_order_id: str
    option_symbol: str
    underlying: str = 'SPY'
    expiry: str = ''
    strike: float = 0.0
    option_type: str = 'CALL'
    side: str
    qty: int
    limit_price: float
    status: str


class Fill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    order_id: int
    fill_price: float
    qty: int


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    option_symbol: str
    underlying: str = 'SPY'
    expiry: str = ''
    strike: float = 0.0
    option_type: str = 'CALL'
    qty: int
    avg_price: float
    mark_price: float
    last_mark_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime
    closed_at: Optional[datetime] = None
    status: str = 'OPEN'


class PnlSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    realized: float
    unrealized: float
    daily_realized: float


class AgentEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime
    event_type: str
    message: str
