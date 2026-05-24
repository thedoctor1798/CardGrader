from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .prices import GradingOpportunityRead, PriceObservationRead
from .centering import CenteringMeasurementRead


class AnalysisRunRead(SQLModel):
    id: int
    owned_card_id: int
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
    created_at: datetime
    completed_at: Optional[datetime] = None


class AnalysisFindingRead(SQLModel):
    id: int
    analysis_run_id: int
    media_id: Optional[int] = None
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
    created_at: datetime


class AnalysisAssetRead(SQLModel):
    id: int
    analysis_run_id: int
    asset_type: Optional[str] = None
    file_path: str
    label: Optional[str] = None
    created_at: datetime


class AnalysisRunDetailRead(SQLModel):
    analysis_run: AnalysisRunRead
    findings: list[AnalysisFindingRead]
    assets: list[AnalysisAssetRead]


class AnalysisReportCardRead(SQLModel):
    id: int
    name: str
    set_name: Optional[str] = None
    set_code: Optional[str] = None
    card_number: Optional[str] = None
    language: Optional[str] = None
    rarity: Optional[str] = None
    variant: Optional[str] = None
    notes: Optional[str] = None


class AnalysisReportOwnedCardRead(SQLModel):
    id: int
    card_id: int
    copy_label: Optional[str] = None
    status: Optional[str] = None
    acquired_price_huf: Optional[int] = None
    acquired_source: Optional[str] = None
    storage_location: Optional[str] = None
    personal_notes: Optional[str] = None


class AnalysisScoresRead(SQLModel):
    centering_score: Optional[float] = None
    corners_score: Optional[float] = None
    edges_score: Optional[float] = None
    surface_score: Optional[float] = None
    overall_score: Optional[float] = None


class AnalysisProbabilitiesRead(SQLModel):
    psa_10_probability: Optional[float] = None
    psa_9_probability: Optional[float] = None
    psa_8_probability: Optional[float] = None
    psa_7_or_lower_probability: Optional[float] = None


class AnalysisGradeRangeRead(SQLModel):
    estimated_grade_low: Optional[str] = None
    estimated_grade_high: Optional[str] = None


class AnalysisReportRead(SQLModel):
    card: AnalysisReportCardRead
    owned_card: AnalysisReportOwnedCardRead
    scores: AnalysisScoresRead
    probabilities: AnalysisProbabilitiesRead
    estimated_grade_range: AnalysisGradeRangeRead
    confidence_level: Optional[str] = None
    human_summary: Optional[str] = None
    recommendation: Optional[str] = None
    recommendation_reason: Optional[str] = None
    latest_price: Optional[PriceObservationRead] = None
    latest_centering: Optional[CenteringMeasurementRead] = None
    opportunity_precheck: Optional[GradingOpportunityRead] = None
    assets: list[AnalysisAssetRead]
    findings: list[AnalysisFindingRead] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    main_grade_limiters: list[str] = Field(default_factory=list)
    manual_review_recommendations: list[str] = Field(default_factory=list)
