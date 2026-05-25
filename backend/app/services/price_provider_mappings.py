from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import Card, PriceProviderCardMapping
from ..models.core import utc_now
from ..schemas import PriceProviderMappingCreate


def normalized_provider(provider: str) -> str:
    return provider.strip().lower()


def get_provider_mapping(session: Session, provider: str, card_id: int) -> PriceProviderCardMapping | None:
    return session.exec(
        select(PriceProviderCardMapping)
        .where(PriceProviderCardMapping.provider == normalized_provider(provider))
        .where(PriceProviderCardMapping.card_id == card_id)
    ).first()


def save_provider_mapping(session: Session, payload: PriceProviderMappingCreate) -> PriceProviderCardMapping:
    if session.get(Card, payload.card_id) is None:
        raise HTTPException(status_code=404, detail={"error": "card_not_found", "message": "Card not found"})
    provider = normalized_provider(payload.provider)
    existing = get_provider_mapping(session, provider, payload.card_id)
    source_card_id = payload.source_card_id.strip()
    mapping = existing or PriceProviderCardMapping(provider=provider, card_id=payload.card_id, source_card_id=source_card_id)
    mapping.source_card_id = source_card_id
    mapping.source_url = payload.source_url
    mapping.confidence = payload.confidence
    mapping.match_score = payload.match_score
    mapping.notes = payload.notes
    mapping.updated_at = utc_now()
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping
