from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import Card, OwnedCard
from ..schemas import OwnedCardCreate, OwnedCardRead

router = APIRouter()


@router.get("/owned-cards", response_model=List[OwnedCardRead])
def list_owned_cards(session: Session = Depends(get_session)):
    return session.exec(select(OwnedCard).order_by(OwnedCard.id)).all()


@router.post("/owned-cards", response_model=OwnedCardRead, status_code=201)
def create_owned_card(
    owned_card_in: OwnedCardCreate,
    session: Session = Depends(get_session),
):
    if session.get(Card, owned_card_in.card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")

    owned_card = OwnedCard(**owned_card_in.dict())
    session.add(owned_card)
    session.commit()
    session.refresh(owned_card)
    return owned_card


@router.get("/owned-cards/{owned_card_id}", response_model=OwnedCardRead)
def get_owned_card(owned_card_id: int, session: Session = Depends(get_session)):
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    return owned_card
