from datetime import date, datetime
from typing import Any, Optional

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


class PriceHistoryRead(SQLModel):
    id: int
    card_id: int
    owned_card_id: Optional[int] = None
    source: str
    source_card_id: Optional[str] = None
    source_url: Optional[str] = None
    raw_price: Optional[float] = None
    market_price: Optional[float] = None
    low_price: Optional[float] = None
    high_price: Optional[float] = None
    psa_7: Optional[float] = None
    psa_8: Optional[float] = None
    psa_9: Optional[float] = None
    psa_10: Optional[float] = None
    currency: str
    converted_currency: Optional[str] = None
    converted_market_price: Optional[float] = None
    converted_raw_price: Optional[float] = None
    converted_psa_7: Optional[float] = None
    converted_psa_8: Optional[float] = None
    converted_psa_9: Optional[float] = None
    converted_psa_10: Optional[float] = None
    confidence: Optional[str] = None
    condition_hint: Optional[str] = None
    fetched_at: datetime
    raw_response_json: Optional[str] = None
    debug_metadata_json: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ManualPriceCreate(SQLModel):
    card_id: int
    owned_card_id: Optional[int] = None
    raw_price: Optional[float] = None
    market_price: Optional[float] = None
    low_price: Optional[float] = None
    high_price: Optional[float] = None
    psa_7: Optional[float] = None
    psa_8: Optional[float] = None
    psa_9: Optional[float] = None
    psa_10: Optional[float] = None
    currency: str = "HUF"
    confidence: Optional[str] = "manual"
    condition_hint: Optional[str] = None
    source_url: Optional[str] = None


class PriceFetchRequest(SQLModel):
    owned_card_id: Optional[int] = None
    sources: Optional[list[str]] = None
    force: bool = False


class PriceFetchResultRead(SQLModel):
    ok: bool
    source: str
    price_history_id: Optional[int] = None
    source_card_id: Optional[str] = None
    source_url: Optional[str] = None
    skipped: bool = False
    match_score: Optional[float] = None
    rate_limit_remaining: Optional[int] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    duration_seconds: Optional[float] = None


class PriceFetchResponse(SQLModel):
    ok: bool
    card_id: int
    fetched_count: int
    failed_count: int
    latest_price: Optional[PriceHistoryRead] = None
    results: list[PriceFetchResultRead]
    error: Optional[str] = None
    message: Optional[str] = None


class PriceLatestResponse(SQLModel):
    ok: bool
    card_id: int
    owned_card_id: Optional[int] = None
    latest: Optional[PriceHistoryRead] = None
    error: Optional[str] = None
    message: Optional[str] = None


class PriceHistoryResponse(SQLModel):
    ok: bool
    card_id: int
    latest: Optional[PriceHistoryRead] = None
    history: list[PriceHistoryRead]


class PriceRefreshResponse(SQLModel):
    ok: bool
    cards_checked: int
    success_count: int
    failure_count: int
    started_at: datetime
    finished_at: datetime
    message: Optional[str] = None


class PriceProviderStatusRead(SQLModel):
    provider: str
    enabled: bool
    configured: bool
    source: str
    missing: list[str] = []
    masked_api_key: Optional[str] = None
    secret_encrypted: bool = False
    plan: Optional[str] = None
    market: Optional[str] = None
    base_url: Optional[str] = None
    daily_limit: Optional[int] = None
    burst_limit: Optional[int] = None
    burst_window_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    cache_ttl_hours: Optional[int] = None
    rate_limit_seconds: Optional[float] = None
    min_match_score: Optional[int] = None
    fetch_history: Optional[bool] = None
    history_period: Optional[str] = None
    respect_retry_after: Optional[bool] = None
    expected_sources: list[str] = []
    path_info: Optional[str] = None


class PriceProvidersStatusResponse(SQLModel):
    ok: bool
    providers: list[PriceProviderStatusRead]


class PriceProviderSettingsUpdate(SQLModel):
    enabled: bool = False
    api_key: Optional[str] = None
    clear_secret: bool = False
    plan: Optional[str] = None
    market: Optional[str] = None
    base_url: Optional[str] = None
    daily_limit: Optional[int] = None
    burst_limit: Optional[int] = None
    burst_window_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    cache_ttl_hours: Optional[int] = None
    rate_limit_seconds: Optional[float] = None
    min_match_score: Optional[int] = None
    fetch_history: Optional[bool] = None
    history_period: Optional[str] = None
    respect_retry_after: Optional[bool] = None


class PriceProviderSettingsResponse(SQLModel):
    ok: bool
    providers: list[PriceProviderStatusRead]


class PriceProviderSettingResponse(SQLModel):
    ok: bool
    provider: PriceProviderStatusRead


class PriceProviderTestResponse(SQLModel):
    ok: bool
    provider: str
    configured: bool
    plan: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None


class CollectionValuationRead(SQLModel):
    ok: bool
    currency: str
    total_value_huf: float
    raw_value_huf: float
    graded_value_huf: float
    owned_cards_count: int
    unique_cards_count: int
    missing_price_cards: int
    price_change_24h_huf: Optional[float] = None
    price_change_7d_huf: Optional[float] = None
    latest_refresh_at: Optional[datetime] = None


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
