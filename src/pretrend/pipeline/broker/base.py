"""Broker abstraction types for paper/live execution."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BrokerBalance:
    cash: float
    total_value: float
    currency: str = "USD"
    fx_usdkrw: Optional[float] = None


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    quantity: float
    avg_price: float
    market_price: Optional[float] = None
    market_value: Optional[float] = None


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    side: str
    quantity: float
    requested_price: Optional[float]
    filled_price: Optional[float]
    status: str
    executed_at: datetime
    raw: Dict[str, Any]


class BrokerAdapter(ABC):
    @abstractmethod
    def get_balance(self) -> BrokerBalance:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        raise NotImplementedError

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        raise NotImplementedError

    def get_usdkrw_rate(self) -> Optional[float]:
        """Optional: return USD/KRW rate if broker can provide it."""
        return None

    def get_orderable_cash_usd(
        self,
        symbol: str,
        *,
        exchange_code: str = "NASD",
        order_price: Optional[float] = None,
    ) -> Optional[float]:
        """Optional: return orderable USD amount for a symbol."""
        return None

    def get_orderable_info(
        self,
        symbol: str,
        *,
        exchange_code: str = "NASD",
        order_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Optional: return raw orderable fields from broker."""
        return {}

    @abstractmethod
    def place_buy_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def place_sell_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> str:
        raise NotImplementedError
