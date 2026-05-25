import re
from datetime import datetime, timedelta

from sqlmodel import Session, select

from ..config import FX_PROVIDER
from ..models import OwnedCard, PriceHistory, PriceObservation
from ..schemas import CollectionValuationRead
from .fx_service import latest_fx_refresh_at
from .price_repository import latest_manual_price, latest_market_price, value_as_huf


def calculate_collection_valuation(session: Session) -> CollectionValuationRead:
    current = calculate_value_at(session, None)
    previous_24h = calculate_value_at(session, datetime.utcnow() - timedelta(hours=24))
    previous_7d = calculate_value_at(session, datetime.utcnow() - timedelta(days=7))

    return CollectionValuationRead(
        ok=True,
        currency="HUF",
        total_value_huf=current["total_value_huf"],
        raw_value_huf=current["raw_value_huf"],
        graded_value_huf=current["graded_value_huf"],
        owned_cards_count=current["owned_cards_count"],
        unique_cards_count=current["unique_cards_count"],
        missing_price_cards=current["missing_price_cards"],
        missing_fx_cards=current["missing_fx_cards"],
        fx_warnings=fx_warnings(int(current["missing_fx_cards"])),
        fx_provider=FX_PROVIDER,
        latest_fx_refresh_at=latest_fx_refresh_at(session),
        price_change_24h_huf=change_from_previous(current, previous_24h),
        price_change_7d_huf=change_from_previous(current, previous_7d),
        latest_refresh_at=latest_refresh_at(session),
    )


def calculate_value_at(session: Session, at_or_before: datetime | None) -> dict[str, float | int]:
    owned_cards = session.exec(select(OwnedCard).order_by(OwnedCard.id)).all()
    total_value_huf = 0.0
    raw_value_huf = 0.0
    graded_value_huf = 0.0
    missing_price_cards = 0
    missing_fx_cards = 0
    priced_cards = 0

    for owned_card in owned_cards:
        value, missing_fx = value_for_owned_card_result(session, owned_card, at_or_before)
        if missing_fx:
            missing_fx_cards += 1
            continue
        if value is None:
            missing_price_cards += 1
            continue
        priced_cards += 1
        total_value_huf += value
        if owned_card.status == "graded_owned":
            graded_value_huf += value
        else:
            raw_value_huf += value

    return {
        "total_value_huf": round(total_value_huf, 2),
        "raw_value_huf": round(raw_value_huf, 2),
        "graded_value_huf": round(graded_value_huf, 2),
        "owned_cards_count": len(owned_cards),
        "unique_cards_count": len({owned_card.card_id for owned_card in owned_cards}),
        "missing_price_cards": missing_price_cards,
        "missing_fx_cards": missing_fx_cards,
        "priced_cards": priced_cards,
    }


def value_for_owned_card(
    session: Session,
    owned_card: OwnedCard,
    at_or_before: datetime | None = None,
) -> float | None:
    value, _missing_fx = value_for_owned_card_result(session, owned_card, at_or_before)
    return value


def value_for_owned_card_result(
    session: Session,
    owned_card: OwnedCard,
    at_or_before: datetime | None = None,
) -> tuple[float | None, bool]:
    market_history = latest_market_price(session, owned_card.card_id, owned_card.id, at_or_before)
    if market_history is not None:
        value = value_from_history(owned_card, market_history)
        if value is not None:
            return value, False
        if has_source_price(market_history) and market_history.currency != "HUF":
            return None, True
        return None, False

    manual_history = latest_manual_price(session, owned_card.card_id, owned_card.id, at_or_before)
    if manual_history is None:
        manual_history = latest_manual_price(session, owned_card.card_id, None, at_or_before)
    if manual_history is not None:
        value = value_from_history(owned_card, manual_history)
        if value is not None:
            return value, False
        if has_source_price(manual_history) and manual_history.currency != "HUF":
            return None, True
        return None, False

    legacy = latest_legacy_price(session, owned_card.card_id, at_or_before)
    if legacy is not None:
        return value_from_legacy(owned_card, legacy), False

    return None, False


def value_from_history(owned_card: OwnedCard, history: PriceHistory) -> float | None:
    raw_value = value_as_huf(history, "market") or value_as_huf(history, "raw")
    if owned_card.status != "graded_owned":
        return raw_value

    grade = parse_psa_grade(owned_card)
    if grade is not None:
        for candidate_grade in range(min(grade, 10), 6, -1):
            graded_value = value_as_huf(history, f"psa_{candidate_grade}")
            if graded_value is not None:
                return graded_value

    return raw_value


def has_source_price(history: PriceHistory) -> bool:
    return any(
        value is not None
        for value in (
            history.raw_price,
            history.market_price,
            history.low_price,
            history.high_price,
            history.psa_7,
            history.psa_8,
            history.psa_9,
            history.psa_10,
        )
    )


def fx_warnings(missing_fx_cards: int) -> list[str]:
    if missing_fx_cards <= 0:
        return []
    return [f"{missing_fx_cards} cards have non-HUF prices but no HUF conversion."]


def value_from_legacy(owned_card: OwnedCard, observation: PriceObservation) -> float | None:
    if owned_card.status != "graded_owned":
        return observation.raw_price_huf

    grade = parse_psa_grade(owned_card)
    if grade is not None:
        grade_values = {
            7: observation.psa_7_price_huf,
            8: observation.psa_8_price_huf,
            9: observation.psa_9_price_huf,
            10: observation.psa_10_price_huf,
        }
        for candidate_grade in range(min(grade, 10), 6, -1):
            if grade_values[candidate_grade] is not None:
                return grade_values[candidate_grade]

    return observation.raw_price_huf


def parse_psa_grade(owned_card: OwnedCard) -> int | None:
    text = " ".join(
        value or ""
        for value in (
            owned_card.status,
            owned_card.copy_label,
            owned_card.personal_notes,
        )
    )
    match = re.search(r"\bpsa\s*(7|8|9|10)\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def latest_legacy_price(
    session: Session,
    card_id: int,
    at_or_before: datetime | None = None,
) -> PriceObservation | None:
    statement = select(PriceObservation).where(PriceObservation.card_id == card_id)
    if at_or_before is not None:
        statement = statement.where(PriceObservation.observed_at <= at_or_before)
    statement = statement.order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    return session.exec(statement).first()


def change_from_previous(current: dict[str, float | int], previous: dict[str, float | int]) -> float | None:
    if previous["priced_cards"] == 0:
        return None
    return round(float(current["total_value_huf"]) - float(previous["total_value_huf"]), 2)


def latest_refresh_at(session: Session) -> datetime | None:
    latest_history = session.exec(
        select(PriceHistory)
        .where(PriceHistory.error_code.is_(None))
        .order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
    ).first()
    if latest_history is not None:
        return latest_history.fetched_at

    latest_legacy = session.exec(
        select(PriceObservation).order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).first()
    return latest_legacy.observed_at if latest_legacy is not None else None
