from datetime import date, datetime
from typing import Any, Optional

from sqlmodel import SQLModel


class CardBase(SQLModel):
    name: str
    set_name: Optional[str] = None
    set_code: Optional[str] = None
    card_number: Optional[str] = None
    language: Optional[str] = None
    rarity: Optional[str] = None
    variant: Optional[str] = None
    notes: Optional[str] = None


class CardCreate(CardBase):
    pass


class CardUpdate(SQLModel):
    name: Optional[str] = None
    set_name: Optional[str] = None
    set_code: Optional[str] = None
    card_number: Optional[str] = None
    language: Optional[str] = None
    rarity: Optional[str] = None
    variant: Optional[str] = None
    notes: Optional[str] = None


class CardRead(CardBase):
    id: int
    created_at: datetime
    updated_at: datetime


class OwnedCardBase(SQLModel):
    card_id: int
    copy_label: Optional[str] = None
    status: Optional[str] = None
    acquired_at: Optional[date] = None
    acquired_price_huf: Optional[int] = None
    acquired_source: Optional[str] = None
    storage_location: Optional[str] = None
    personal_notes: Optional[str] = None


class OwnedCardCreate(OwnedCardBase):
    pass


class OwnedCardUpdate(SQLModel):
    card_id: Optional[int] = None
    copy_label: Optional[str] = None
    status: Optional[str] = None
    acquired_at: Optional[date] = None
    acquired_price_huf: Optional[int] = None
    acquired_source: Optional[str] = None
    storage_location: Optional[str] = None
    personal_notes: Optional[str] = None


class OwnedCardRead(OwnedCardBase):
    id: int
    created_at: datetime
    updated_at: datetime


class CardMediaRead(SQLModel):
    id: int
    owned_card_id: int
    media_type: str
    label: str
    file_path: str
    original_filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: Optional[int] = None
    derived_from_media_id: Optional[int] = None
    edit_type: Optional[str] = None
    edit_metadata: Optional[str] = None
    created_at: datetime


class DerivedMediaCreate(SQLModel):
    label: Optional[str] = None
    edit_type: str = "manual_adjustment"
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0
    gamma: float = 1.0
    exposure: float = 0.0
    rotate_degrees: float = 0.0
    crop_x: Optional[float] = None
    crop_y: Optional[float] = None
    crop_width: Optional[float] = None
    crop_height: Optional[float] = None
    edit_metadata: Optional[dict[str, Any]] = None
