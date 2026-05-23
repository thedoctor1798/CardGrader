from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..models import Card, OwnedCard

router = APIRouter()


@router.post("/demo/seed-rowlet", status_code=201)
def seed_rowlet(session: Session = Depends(get_session)):
    card = Card(
        name="Rowlet",
        set_name="ME03: Perfect Order",
        set_code="POR",
        card_number="090/088",
    )
    session.add(card)
    session.commit()
    session.refresh(card)

    owned_card = OwnedCard(
        card_id=card.id,
        copy_label="Rowlet demo copy",
        status="raw_owned",
        acquired_source="unknown",
    )
    session.add(owned_card)
    session.commit()
    session.refresh(owned_card)

    return {"card": card, "owned_card": owned_card}
