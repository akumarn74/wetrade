from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class BrokerOrder:
    option_symbol: str
    side: str
    qty: int
    limit_price: float
    underlying: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None


@dataclass
class BrokerOrderResult:
    broker_order_id: str
    status: str


class BrokerPort(ABC):
    @abstractmethod
    def place_limit_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError

    def try_fill(self, broker_order_id: str, mark_price: float) -> tuple[bool, float]:
        return False, 0.0
