from datetime import date, datetime
from typing import Optional

from sqlmodel import SQLModel


class PriceObservationCreate(SQLModel):
    source_name: str = "manual"
    currency: str = "HUF"
    raw_price_huf: Optional[float] = None
    psa_7_price_huf: Optional[float] = None
    psa_8_price_huf: Optional[float] = None
    psa_9_price_huf: Optional[float] = None
    psa_10_price_huf: Optional[float] = None
    price_confidence: float = 0.5
    observed_at: Optional[datetime] = None
    notes: Optional[str] = None


class PriceObservationRead(SQLModel):
    id: int
    card_id: int
    owned_card_id: Optional[int] = None
    source_name: Optional[str] = None
    currency: Optional[str] = None
    raw_price_huf: Optional[float] = None
    psa_7_price_huf: Optional[float] = None
    psa_8_price_huf: Optional[float] = None
    psa_9_price_huf: Optional[float] = None
    psa_10_price_huf: Optional[float] = None
    price_confidence: Optional[float] = None
    observed_at: datetime
    notes: Optional[str] = None


class CollectionSummaryRead(SQLModel):
    total_cards: int
    unique_cards: int
    raw_cards: int
    graded_cards: int
    collection_value_huf: float
    cost_basis_huf: float
    unrealized_profit_huf: float
    conservative_value_huf: float
    expected_value_huf: float
    optimistic_value_huf: float
    cards_missing_price_total: int


class CollectionSnapshotRead(SQLModel):
    id: int
    snapshot_date: date
    total_cards: Optional[int] = None
    unique_cards: Optional[int] = None
    raw_cards: Optional[int] = None
    graded_cards: Optional[int] = None
    collection_value_huf: Optional[float] = None
    cost_basis_huf: Optional[float] = None
    unrealized_profit_huf: Optional[float] = None
    conservative_value_huf: Optional[float] = None
    expected_value_huf: Optional[float] = None
    optimistic_value_huf: Optional[float] = None
    created_at: datetime


class GradingOpportunityRead(SQLModel):
    raw_price_huf: Optional[float] = None
    psa_7_price_huf: Optional[float] = None
    psa_8_price_huf: Optional[float] = None
    psa_9_price_huf: Optional[float] = None
    psa_10_price_huf: Optional[float] = None
    grading_cost_huf: float
    profit_if_psa_7: Optional[float] = None
    profit_if_psa_8: Optional[float] = None
    profit_if_psa_9: Optional[float] = None
    profit_if_psa_10: Optional[float] = None
    minimum_profitable_grade: Optional[str] = None
    opportunity_score: int
    recommendation: str
