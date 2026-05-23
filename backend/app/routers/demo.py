from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import Card, OwnedCard

router = APIRouter()


@router.post("/demo/seed-rowlet", status_code=201)
def seed_rowlet(session: Session = Depends(get_session)):
    card_statement = (
        select(Card)
        .where(Card.name == "Rowlet")
        .where(Card.set_name == "ME03: Perfect Order")
        .where(Card.set_code == "POR")
        .where(Card.card_number == "090/088")
        .order_by(Card.id)
    )
    card = session.exec(card_statement).first()
    created = False
    if card is None:
        card = Card(
            name="Rowlet",
            set_name="ME03: Perfect Order",
            set_code="POR",
            card_number="090/088",
        )
        session.add(card)
        session.commit()
        session.refresh(card)
        created = True

    owned_card_statement = (
        select(OwnedCard)
        .where(OwnedCard.card_id == card.id)
        .where(OwnedCard.copy_label == "Rowlet demo copy")
        .order_by(OwnedCard.id)
    )
    owned_card = session.exec(owned_card_statement).first()
    if owned_card is None:
        owned_card = OwnedCard(
            card_id=card.id,
            copy_label="Rowlet demo copy",
            status="raw_owned",
            acquired_source="unknown",
        )
        session.add(owned_card)
        session.commit()
        session.refresh(owned_card)
        created = True

    return {"card": card, "owned_card": owned_card, "created": created}
