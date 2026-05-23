from datetime import date, datetime
from typing import Optional

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


class OwnedCardRead(OwnedCardBase):
    id: int
    created_at: datetime
    updated_at: datetime
