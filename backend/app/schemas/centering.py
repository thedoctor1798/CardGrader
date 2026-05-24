from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel


class CenteringMeasurementCreate(SQLModel):
    analysis_run_id: Optional[int] = None
    media_id: Optional[int] = None
    side: str = "front"
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
    notes: Optional[str] = None


class CenteringMeasurementRead(CenteringMeasurementCreate):
    id: int
    owned_card_id: int
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
    created_at: datetime
    updated_at: datetime
