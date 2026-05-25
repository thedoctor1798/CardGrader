from datetime import datetime
from typing import Any, Optional

from sqlmodel import SQLModel


class RecognitionExtractedRead(SQLModel):
    name: Optional[str] = None
    card_number: Optional[str] = None
    set_text: Optional[str] = None
    set_code: Optional[str] = None
    rarity: Optional[str] = None
    language: Optional[str] = None


class RecognitionAttemptRead(SQLModel):
    id: int
    media_id: int
    owned_card_id: Optional[int] = None
    status: str
    mode: str
    extracted: RecognitionExtractedRead
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RecognitionCandidateRead(SQLModel):
    id: int
    recognition_attempt_id: int
    catalog_card_id: int
    rank: int
    score: float
    name: str
    set_name: Optional[str] = None
    set_code: Optional[str] = None
    card_number: Optional[str] = None
    rarity: Optional[str] = None
    language: Optional[str] = None
    thumbnail_file_path: Optional[str] = None
    match_reasons: list[str]
    name_score: Optional[float] = None
    number_score: Optional[float] = None
    set_score: Optional[float] = None
    rarity_score: Optional[float] = None
    language_score: Optional[float] = None


class RecognitionResponse(SQLModel):
    ok: bool
    recognition_attempt: Optional[RecognitionAttemptRead] = None
    candidates: list[RecognitionCandidateRead] = []
    error: Optional[str] = None
    message: Optional[str] = None
    recognition_attempt_id: Optional[int] = None


class RecognitionAcceptRequest(SQLModel):
    catalog_card_id: int
    owned_card_id: Optional[int] = None
    create_owned_card: bool = False


class RecognitionAcceptResponse(SQLModel):
    ok: bool
    owned_card: dict[str, Any]
