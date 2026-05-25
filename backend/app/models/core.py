from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.utcnow()


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    set_name: Optional[str] = None
    set_code: Optional[str] = None
    card_number: Optional[str] = None
    language: Optional[str] = None
    rarity: Optional[str] = None
    variant: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OwnedCard(SQLModel, table=True):
    __tablename__ = "owned_cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id")
    copy_label: Optional[str] = None
    status: Optional[str] = None
    acquired_at: Optional[date] = None
    acquired_price_huf: Optional[int] = None
    acquired_source: Optional[str] = None
    storage_location: Optional[str] = None
    personal_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CardMedia(SQLModel, table=True):
    __tablename__ = "card_media"

    id: Optional[int] = Field(default=None, primary_key=True)
    owned_card_id: Optional[int] = Field(default=None, foreign_key="owned_cards.id")
    media_type: Optional[str] = None
    label: Optional[str] = None
    file_path: str
    original_filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: Optional[int] = None
    derived_from_media_id: Optional[int] = Field(default=None, foreign_key="card_media.id")
    edit_type: Optional[str] = None
    edit_metadata: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class PriceObservation(SQLModel, table=True):
    __tablename__ = "price_observations"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id")
    owned_card_id: Optional[int] = Field(default=None, foreign_key="owned_cards.id")
    source_name: Optional[str] = None
    currency: Optional[str] = None
    raw_price_huf: Optional[float] = None
    psa_7_price_huf: Optional[float] = None
    psa_8_price_huf: Optional[float] = None
    psa_9_price_huf: Optional[float] = None
    psa_10_price_huf: Optional[float] = None
    price_confidence: Optional[float] = None
    observed_at: datetime = Field(default_factory=utc_now)
    notes: Optional[str] = None


class PriceHistory(SQLModel, table=True):
    __tablename__ = "price_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    owned_card_id: Optional[int] = Field(default=None, foreign_key="owned_cards.id", index=True)
    source: str = Field(index=True)
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
    currency: str = Field(default="HUF", index=True)
    converted_currency: Optional[str] = None
    converted_market_price: Optional[float] = None
    converted_raw_price: Optional[float] = None
    converted_psa_7: Optional[float] = None
    converted_psa_8: Optional[float] = None
    converted_psa_9: Optional[float] = None
    converted_psa_10: Optional[float] = None
    confidence: Optional[str] = None
    condition_hint: Optional[str] = None
    fetched_at: datetime = Field(default_factory=utc_now, index=True)
    raw_response_json: Optional[str] = None
    debug_metadata_json: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalysisRun(SQLModel, table=True):
    __tablename__ = "analysis_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    owned_card_id: int = Field(foreign_key="owned_cards.id")
    mode: Optional[str] = None
    status: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    opencv_version: Optional[str] = None
    analysis_version: Optional[str] = None
    centering_score: Optional[float] = None
    corners_score: Optional[float] = None
    edges_score: Optional[float] = None
    surface_score: Optional[float] = None
    overall_score: Optional[float] = None
    estimated_grade_low: Optional[str] = None
    estimated_grade_high: Optional[str] = None
    psa_10_probability: Optional[float] = None
    psa_9_probability: Optional[float] = None
    psa_8_probability: Optional[float] = None
    psa_7_or_lower_probability: Optional[float] = None
    confidence_level: Optional[str] = None
    human_summary: Optional[str] = None
    recommendation: Optional[str] = None
    recommendation_reason: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class AnalysisFinding(SQLModel, table=True):
    __tablename__ = "analysis_findings"

    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_run_id: int = Field(foreign_key="analysis_runs.id")
    media_id: Optional[int] = Field(default=None, foreign_key="card_media.id")
    finding_type: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[float] = None
    location_label: Optional[str] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_width: Optional[float] = None
    bbox_height: Optional[float] = None
    title: Optional[str] = None
    description: Optional[str] = None
    grade_impact: Optional[str] = None
    side: Optional[str] = None
    confirmed: Optional[bool] = None
    uncertainty_reason: Optional[str] = None
    photo_quality_issue: Optional[bool] = None
    created_at: datetime = Field(default_factory=utc_now)


class AnalysisAsset(SQLModel, table=True):
    __tablename__ = "analysis_assets"

    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_run_id: int = Field(foreign_key="analysis_runs.id")
    asset_type: Optional[str] = None
    file_path: str
    label: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class CollectionSnapshot(SQLModel, table=True):
    __tablename__ = "collection_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
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
    created_at: datetime = Field(default_factory=utc_now)


class CenteringMeasurement(SQLModel, table=True):
    __tablename__ = "centering_measurements"

    id: Optional[int] = Field(default=None, primary_key=True)
    owned_card_id: int = Field(foreign_key="owned_cards.id")
    analysis_run_id: Optional[int] = Field(default=None, foreign_key="analysis_runs.id")
    media_id: Optional[int] = Field(default=None, foreign_key="card_media.id")
    side: str
    source: str = "manual"
    image_label: Optional[str] = None
    image_width: int
    image_height: int
    outer_left_px: float
    outer_right_px: float
    outer_top_px: float
    outer_bottom_px: float
    inner_left_px: float
    inner_right_px: float
    inner_top_px: float
    inner_bottom_px: float
    outer_left_pct: Optional[float] = None
    outer_right_pct: Optional[float] = None
    outer_top_pct: Optional[float] = None
    outer_bottom_pct: Optional[float] = None
    inner_left_pct: Optional[float] = None
    inner_right_pct: Optional[float] = None
    inner_top_pct: Optional[float] = None
    inner_bottom_pct: Optional[float] = None
    left_border_px: Optional[float] = None
    right_border_px: Optional[float] = None
    top_border_px: Optional[float] = None
    bottom_border_px: Optional[float] = None
    horizontal_ratio_label: Optional[str] = None
    vertical_ratio_label: Optional[str] = None
    horizontal_left_percent: Optional[float] = None
    horizontal_right_percent: Optional[float] = None
    vertical_top_percent: Optional[float] = None
    vertical_bottom_percent: Optional[float] = None
    horizontal_offcenter_percent: Optional[float] = None
    vertical_offcenter_percent: Optional[float] = None
    centering_score: Optional[float] = None
    estimated_grade_label: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RecognitionAttempt(SQLModel, table=True):
    __tablename__ = "recognition_attempts"

    id: Optional[int] = Field(default=None, primary_key=True)
    media_id: int = Field(foreign_key="card_media.id", index=True)
    owned_card_id: Optional[int] = Field(default=None, foreign_key="owned_cards.id", index=True)
    status: str = Field(default="pending", index=True)
    mode: str = Field(default="remote_worker")
    extracted_name: Optional[str] = None
    extracted_card_number: Optional[str] = None
    extracted_set_text: Optional[str] = None
    extracted_set_code: Optional[str] = None
    extracted_rarity: Optional[str] = None
    extracted_language: Optional[str] = None
    extracted_raw_json: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RecognitionCandidate(SQLModel, table=True):
    __tablename__ = "recognition_candidates"

    id: Optional[int] = Field(default=None, primary_key=True)
    recognition_attempt_id: int = Field(foreign_key="recognition_attempts.id", index=True)
    catalog_card_id: int = Field(foreign_key="cards.id", index=True)
    score: float = Field(default=0.0, index=True)
    rank: int = Field(default=0, index=True)
    match_reasons: Optional[str] = None
    name_score: Optional[float] = None
    number_score: Optional[float] = None
    set_score: Optional[float] = None
    rarity_score: Optional[float] = None
    language_score: Optional[float] = None
    created_at: datetime = Field(default_factory=utc_now)
