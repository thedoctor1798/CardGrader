from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import GradingOpportunityRead, PriceObservationCreate, PriceObservationRead
from ..services.pricing import (
    calculate_grading_opportunity,
    create_price_observation,
    latest_price_for_owned_card,
    list_price_observations,
    require_latest_price_for_card,
)

router = APIRouter()


@router.post("/cards/{card_id}/prices", response_model=PriceObservationRead, status_code=201)
def create_card_price(
    card_id: int,
    price_in: PriceObservationCreate,
    session: Session = Depends(get_session),
):
    return create_price_observation(session, card_id, price_in)


@router.get("/cards/{card_id}/prices", response_model=List[PriceObservationRead])
def list_card_prices(card_id: int, session: Session = Depends(get_session)):
    return list_price_observations(session, card_id)


@router.get("/cards/{card_id}/latest-price", response_model=PriceObservationRead)
def get_card_latest_price(card_id: int, session: Session = Depends(get_session)):
    return require_latest_price_for_card(session, card_id)


@router.get("/owned-cards/{owned_card_id}/latest-price", response_model=PriceObservationRead)
def get_owned_card_latest_price(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return latest_price_for_owned_card(session, owned_card_id)


@router.get("/cards/{card_id}/opportunity", response_model=GradingOpportunityRead)
def get_card_grading_opportunity(card_id: int, session: Session = Depends(get_session)):
    return calculate_grading_opportunity(session, card_id)
