from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import Card, CollectionSnapshot, OwnedCard, PriceObservation
from ..schemas import CollectionSummaryRead, GradingOpportunityRead, PriceObservationCreate

DEFAULT_GRADING_COST_HUF = 13000.0
PRICE_FIELDS = (
    "raw_price_huf",
    "psa_7_price_huf",
    "psa_8_price_huf",
    "psa_9_price_huf",
    "psa_10_price_huf",
)


def validate_price_observation(price_in: PriceObservationCreate) -> None:
    if not 0.0 <= price_in.price_confidence <= 1.0:
        raise HTTPException(
            status_code=400,
            detail="price_confidence must be between 0.0 and 1.0",
        )

    for field_name in PRICE_FIELDS:
        value = getattr(price_in, field_name)
        if value is not None and value < 0:
            raise HTTPException(status_code=400, detail=f"{field_name} cannot be negative")


def get_latest_price_for_card(session: Session, card_id: int) -> Optional[PriceObservation]:
    statement = (
        select(PriceObservation)
        .where(PriceObservation.card_id == card_id)
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    )
    return session.exec(statement).first()


def require_card(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def require_owned_card(session: Session, owned_card_id: int) -> OwnedCard:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    return owned_card


def create_price_observation(
    session: Session,
    card_id: int,
    price_in: PriceObservationCreate,
) -> PriceObservation:
    require_card(session, card_id)
    validate_price_observation(price_in)

    price = PriceObservation(
        card_id=card_id,
        source_name=price_in.source_name,
        currency=price_in.currency,
        raw_price_huf=price_in.raw_price_huf,
        psa_7_price_huf=price_in.psa_7_price_huf,
        psa_8_price_huf=price_in.psa_8_price_huf,
        psa_9_price_huf=price_in.psa_9_price_huf,
        psa_10_price_huf=price_in.psa_10_price_huf,
        price_confidence=price_in.price_confidence,
        observed_at=price_in.observed_at or datetime.utcnow(),
        notes=price_in.notes,
    )
    session.add(price)
    session.commit()
    session.refresh(price)
    return price


def list_price_observations(session: Session, card_id: int) -> list[PriceObservation]:
    require_card(session, card_id)
    statement = (
        select(PriceObservation)
        .where(PriceObservation.card_id == card_id)
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    )
    return session.exec(statement).all()


def require_latest_price_for_card(session: Session, card_id: int) -> PriceObservation:
    require_card(session, card_id)
    price = get_latest_price_for_card(session, card_id)
    if price is None:
        raise HTTPException(status_code=404, detail="No price observation found for card")
    return price


def latest_price_for_owned_card(session: Session, owned_card_id: int) -> PriceObservation:
    owned_card = require_owned_card(session, owned_card_id)
    price = get_latest_price_for_card(session, owned_card.card_id)
    if price is None:
        raise HTTPException(status_code=404, detail="No price observation found for owned card")
    return price


def calculate_collection_summary(session: Session) -> CollectionSummaryRead:
    from .valuation_service import calculate_collection_valuation

    owned_cards = session.exec(select(OwnedCard)).all()
    total_cards = len(owned_cards)
    unique_cards = len({owned_card.card_id for owned_card in owned_cards})
    raw_cards = sum(1 for owned_card in owned_cards if owned_card.status == "raw_owned")
    graded_cards = sum(1 for owned_card in owned_cards if owned_card.status == "graded_owned")
    cost_basis_huf = sum(
        float(owned_card.acquired_price_huf)
        for owned_card in owned_cards
        if owned_card.acquired_price_huf is not None
    )

    valuation = calculate_collection_valuation(session)
    collection_value_huf = valuation.total_value_huf
    optimistic_value_huf = valuation.total_value_huf

    return CollectionSummaryRead(
        total_cards=total_cards,
        unique_cards=unique_cards,
        raw_cards=raw_cards,
        graded_cards=graded_cards,
        collection_value_huf=collection_value_huf,
        cost_basis_huf=cost_basis_huf,
        unrealized_profit_huf=collection_value_huf - cost_basis_huf,
        conservative_value_huf=collection_value_huf,
        expected_value_huf=collection_value_huf,
        optimistic_value_huf=optimistic_value_huf,
        cards_missing_price_total=valuation.missing_price_cards,
    )


def create_collection_snapshot(session: Session) -> CollectionSnapshot:
    summary = calculate_collection_summary(session)
    snapshot = CollectionSnapshot(
        snapshot_date=date.today(),
        total_cards=summary.total_cards,
        unique_cards=summary.unique_cards,
        raw_cards=summary.raw_cards,
        graded_cards=summary.graded_cards,
        collection_value_huf=summary.collection_value_huf,
        cost_basis_huf=summary.cost_basis_huf,
        unrealized_profit_huf=summary.unrealized_profit_huf,
        conservative_value_huf=summary.conservative_value_huf,
        expected_value_huf=summary.expected_value_huf,
        optimistic_value_huf=summary.optimistic_value_huf,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def list_collection_snapshots(session: Session) -> list[CollectionSnapshot]:
    statement = select(CollectionSnapshot).order_by(
        CollectionSnapshot.created_at.desc(),
        CollectionSnapshot.id.desc(),
    )
    return session.exec(statement).all()


def profit_for_grade(raw_price: Optional[float], grade_price: Optional[float]) -> Optional[float]:
    if raw_price is None or grade_price is None:
        return None
    return float(grade_price) - float(raw_price) - DEFAULT_GRADING_COST_HUF


def minimum_profitable_grade(profits: dict[str, Optional[float]]) -> Optional[str]:
    for grade in ("psa_7", "psa_8", "psa_9", "psa_10"):
        profit = profits[grade]
        if profit is not None and profit > 0:
            return grade.upper()
    return None


def calculate_grading_opportunity(session: Session, card_id: int) -> GradingOpportunityRead:
    latest_price = require_latest_price_for_card(session, card_id)
    raw_price = latest_price.raw_price_huf
    profits = {
        "psa_7": profit_for_grade(raw_price, latest_price.psa_7_price_huf),
        "psa_8": profit_for_grade(raw_price, latest_price.psa_8_price_huf),
        "psa_9": profit_for_grade(raw_price, latest_price.psa_9_price_huf),
        "psa_10": profit_for_grade(raw_price, latest_price.psa_10_price_huf),
    }

    psa_prices = (
        latest_price.psa_7_price_huf,
        latest_price.psa_8_price_huf,
        latest_price.psa_9_price_huf,
        latest_price.psa_10_price_huf,
    )
    if raw_price is None or all(price is None for price in psa_prices):
        recommendation = "insufficient_price_data"
    elif profits["psa_10"] is not None and profits["psa_10"] <= 0:
        recommendation = "do_not_grade"
    elif profits["psa_9"] is not None and profits["psa_9"] > 0:
        recommendation = "good_grade_candidate"
    elif profits["psa_10"] is not None and profits["psa_10"] > 0:
        recommendation = "borderline_grade_candidate"
    else:
        recommendation = "collection_only"

    score = 0
    if raw_price is not None:
        score += 25
    if latest_price.psa_10_price_huf is not None and (profits["psa_10"] or 0) > 0:
        score += 25
    if latest_price.psa_9_price_huf is not None and (profits["psa_9"] or 0) > 0:
        score += 25
    if latest_price.psa_8_price_huf is not None and (profits["psa_8"] or 0) > 0:
        score += 15
    if latest_price.price_confidence is not None and latest_price.price_confidence >= 0.7:
        score += 10

    return GradingOpportunityRead(
        raw_price_huf=raw_price,
        psa_7_price_huf=latest_price.psa_7_price_huf,
        psa_8_price_huf=latest_price.psa_8_price_huf,
        psa_9_price_huf=latest_price.psa_9_price_huf,
        psa_10_price_huf=latest_price.psa_10_price_huf,
        grading_cost_huf=DEFAULT_GRADING_COST_HUF,
        profit_if_psa_7=profits["psa_7"],
        profit_if_psa_8=profits["psa_8"],
        profit_if_psa_9=profits["psa_9"],
        profit_if_psa_10=profits["psa_10"],
        minimum_profitable_grade=minimum_profitable_grade(profits),
        opportunity_score=min(score, 100),
        recommendation=recommendation,
    )
