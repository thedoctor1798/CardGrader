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
    owned_card_id: int = Field(foreign_key="owned_cards.id")
    media_type: Optional[str] = None
    label: Optional[str] = None
    file_path: str
    original_filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)


class PriceObservation(SQLModel, table=True):
    __tablename__ = "price_observations"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id")
    owned_card_id: Optional[int] = Field(default=None, foreign_key="owned_cards.id")
    source_name: Optional[str] = None
    currency: Optional[str] = None
    raw_price_huf: Optional[int] = None
    psa_7_price_huf: Optional[int] = None
    psa_8_price_huf: Optional[int] = None
    psa_9_price_huf: Optional[int] = None
    psa_10_price_huf: Optional[int] = None
    price_confidence: Optional[float] = None
    observed_at: datetime = Field(default_factory=utc_now)
    notes: Optional[str] = None


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
    estimated_grade_low: Optional[float] = None
    estimated_grade_high: Optional[float] = None
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
    grade_impact: Optional[float] = None
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
    collection_value_huf: Optional[int] = None
    cost_basis_huf: Optional[int] = None
    unrealized_profit_huf: Optional[int] = None
    conservative_value_huf: Optional[int] = None
    expected_value_huf: Optional[int] = None
    optimistic_value_huf: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)
