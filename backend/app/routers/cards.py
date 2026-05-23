from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import Card
from ..schemas import CardCreate, CardRead

router = APIRouter()


@router.get("/cards", response_model=List[CardRead])
def list_cards(session: Session = Depends(get_session)):
    return session.exec(select(Card).order_by(Card.id)).all()


@router.post("/cards", response_model=CardRead, status_code=201)
def create_card(card_in: CardCreate, session: Session = Depends(get_session)):
    card = Card(**card_in.dict())
    session.add(card)
    session.commit()
    session.refresh(card)
    return card


@router.get("/cards/{card_id}", response_model=CardRead)
def get_card(card_id: int, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card
