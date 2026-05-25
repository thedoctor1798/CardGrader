from dataclasses import dataclass, field
from typing import Any, Optional

from sqlmodel import Session

from ...models import Card


@dataclass
class PriceData:
    raw_price: Optional[float] = None
    market_price: Optional[float] = None
    low_price: Optional[float] = None
    high_price: Optional[float] = None
    psa_7: Optional[float] = None
    psa_8: Optional[float] = None
    psa_9: Optional[float] = None
    psa_10: Optional[float] = None
    currency: str = "HUF"

    def has_any_price(self) -> bool:
        return any(
            value is not None
            for value in (
                self.raw_price,
                self.market_price,
                self.low_price,
                self.high_price,
                self.psa_7,
                self.psa_8,
                self.psa_9,
                self.psa_10,
            )
        )


@dataclass
class PriceSourceResult:
    ok: bool
    source: str
    card_id: int
    source_card_id: Optional[str] = None
    source_url: Optional[str] = None
    prices: Optional[PriceData] = None
    confidence: Optional[str] = None
    condition_hint: Optional[str] = None
    raw_response: Any = None
    debug_metadata: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    match_score: Optional[float] = None
    rate_limit_remaining: Optional[int] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class PriceSource:
    source_name = "base"

    def fetch(
        self,
        session: Session,
        card: Card,
        owned_card_id: int | None = None,
    ) -> PriceSourceResult:
        raise NotImplementedError
