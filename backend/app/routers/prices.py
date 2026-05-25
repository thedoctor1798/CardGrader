from typing import List

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..database import get_session
from ..schemas import (
    ManualPriceCreate,
    PriceFetchRequest,
    PriceFetchResponse,
    PriceHistoryRead,
    PriceHistoryResponse,
    PriceLatestResponse,
    PriceObservationCreate,
    PriceObservationRead,
    PriceProvidersStatusResponse,
    PriceRefreshResponse,
    GradingOpportunityRead,
)
from ..services.price_repository import create_manual_price, latest_successful_price, list_price_history, require_card, require_owned_card
from ..services.price_service import fetch_prices_for_card, price_provider_statuses, refresh_prices
from ..services.pricing import (
    calculate_grading_opportunity,
    create_price_observation,
    latest_price_for_owned_card,
    list_price_observations,
    require_latest_price_for_card,
)

router = APIRouter()


@router.post("/prices/fetch/{card_id}", response_model=PriceFetchResponse)
def fetch_card_prices(
    card_id: int,
    payload: PriceFetchRequest | None = None,
    session: Session = Depends(get_session),
):
    return fetch_prices_for_card(session, card_id, payload)


@router.post("/prices/manual", response_model=PriceHistoryRead, status_code=201)
def create_manual_card_price(
    payload: ManualPriceCreate,
    session: Session = Depends(get_session),
):
    return create_manual_price(session, payload)


@router.get("/prices/providers/status", response_model=PriceProvidersStatusResponse)
def get_price_provider_status(session: Session = Depends(get_session)):
    return price_provider_statuses(session)


@router.get("/prices/latest/{card_id}", response_model=PriceLatestResponse)
def get_latest_card_price_history(card_id: int, session: Session = Depends(get_session)):
    require_card(session, card_id)
    latest = latest_successful_price(session, card_id)
    if latest is None:
        return PriceLatestResponse(
            ok=False,
            card_id=card_id,
            latest=None,
            error="no_price_history",
            message="No price history found for card.",
        )
    return PriceLatestResponse(ok=True, card_id=card_id, latest=latest)


@router.get("/owned-cards/{owned_card_id}/prices/latest", response_model=PriceLatestResponse)
def get_latest_owned_card_price_history(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    owned_card = require_owned_card(session, owned_card_id)
    latest = latest_successful_price(session, owned_card.card_id, owned_card.id)
    if latest is None:
        return PriceLatestResponse(
            ok=False,
            card_id=owned_card.card_id,
            owned_card_id=owned_card.id,
            latest=None,
            error="no_price_history",
            message="No price history found for owned card.",
        )
    return PriceLatestResponse(ok=True, card_id=owned_card.card_id, owned_card_id=owned_card.id, latest=latest)


@router.get("/prices/history/{card_id}", response_model=PriceHistoryResponse)
def get_card_price_history(
    card_id: int,
    source: str | None = None,
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    currency: str | None = None,
    session: Session = Depends(get_session),
):
    history = list_price_history(session, card_id, source=source, currency=currency, from_dt=from_dt, to_dt=to_dt)
    latest = latest_successful_price(session, card_id)
    return PriceHistoryResponse(ok=True, card_id=card_id, latest=latest, history=history)


@router.post("/prices/refresh-all", response_model=PriceRefreshResponse)
def refresh_all_prices(session: Session = Depends(get_session)):
    return refresh_prices(session, owned_only=False)


@router.post("/prices/refresh-owned", response_model=PriceRefreshResponse)
def refresh_owned_prices(session: Session = Depends(get_session)):
    return refresh_prices(session, owned_only=True)


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
