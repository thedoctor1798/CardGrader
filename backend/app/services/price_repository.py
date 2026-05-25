import json
import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import PRICE_DEFAULT_CURRENCY, PRICE_FX_EUR_HUF, PRICE_FX_USD_HUF
from ..models import Card, OwnedCard, PriceHistory, PriceObservation
from ..models.core import utc_now
from ..schemas import ManualPriceCreate
from .price_sources import PriceData, PriceSourceResult

PRICE_VALUE_FIELDS = (
    "raw_price",
    "market_price",
    "low_price",
    "high_price",
    "psa_7",
    "psa_8",
    "psa_9",
    "psa_10",
)

SUPPORTED_CURRENCIES = {"HUF", "EUR", "USD"}
logger = logging.getLogger(__name__)


def require_card(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail={"error": "card_not_found", "message": "Card not found"})
    return card


def require_owned_card(session: Session, owned_card_id: int) -> OwnedCard:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail={"error": "owned_card_not_found", "message": "Owned card not found"})
    return owned_card


def validate_owned_card_for_card(session: Session, owned_card_id: int | None, card_id: int) -> OwnedCard | None:
    if owned_card_id is None:
        return None
    owned_card = require_owned_card(session, owned_card_id)
    if owned_card.card_id != card_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "owned_card_card_mismatch", "message": "Owned card does not belong to the requested card."},
        )
    return owned_card


def validate_currency(currency: str) -> str:
    normalized = (currency or PRICE_DEFAULT_CURRENCY).strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail={"error": "unsupported_currency", "message": f"Unsupported currency: {currency}"},
        )
    return normalized


def validate_price_values(values: dict[str, float | None]) -> None:
    if not any(value is not None for value in values.values()):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_manual_price_payload", "message": "At least one price field is required."},
        )
    for field_name, value in values.items():
        if value is not None and value < 0:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_manual_price_payload", "message": f"{field_name} cannot be negative."},
            )


def json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, default=str)


def apply_currency_conversion(prices: PriceData, debug_metadata: dict[str, Any]) -> dict[str, Any]:
    currency = validate_currency(prices.currency)
    if currency == "HUF":
        return {
            "converted_currency": "HUF",
            "converted_market_price": prices.market_price,
            "converted_raw_price": prices.raw_price,
            "converted_psa_7": prices.psa_7,
            "converted_psa_8": prices.psa_8,
            "converted_psa_9": prices.psa_9,
            "converted_psa_10": prices.psa_10,
        }

    fx_rate = {"EUR": PRICE_FX_EUR_HUF, "USD": PRICE_FX_USD_HUF}.get(currency)
    if fx_rate is None:
        debug_metadata["fx"] = {"currency": currency, "target": "HUF", "configured": False}
        return {
            "converted_currency": None,
            "converted_market_price": None,
            "converted_raw_price": None,
            "converted_psa_7": None,
            "converted_psa_8": None,
            "converted_psa_9": None,
            "converted_psa_10": None,
        }

    debug_metadata["fx"] = {"currency": currency, "target": "HUF", "configured": True, "rate": fx_rate}
    return {
        "converted_currency": "HUF",
        "converted_market_price": convert_price(prices.market_price, fx_rate),
        "converted_raw_price": convert_price(prices.raw_price, fx_rate),
        "converted_psa_7": convert_price(prices.psa_7, fx_rate),
        "converted_psa_8": convert_price(prices.psa_8, fx_rate),
        "converted_psa_9": convert_price(prices.psa_9, fx_rate),
        "converted_psa_10": convert_price(prices.psa_10, fx_rate),
    }


def convert_price(value: float | None, fx_rate: float) -> float | None:
    return None if value is None else round(float(value) * fx_rate, 2)


def save_source_result(
    session: Session,
    card_id: int,
    owned_card_id: int | None,
    result: PriceSourceResult,
    duration_seconds: float | None = None,
) -> PriceHistory:
    debug_metadata = dict(result.debug_metadata or {})
    if duration_seconds is not None:
        debug_metadata["request_duration_seconds"] = duration_seconds

    prices = result.prices or PriceData(currency=PRICE_DEFAULT_CURRENCY)
    currency = validate_currency(prices.currency)
    conversion = apply_currency_conversion(prices, debug_metadata) if result.ok else {
        "converted_currency": None,
        "converted_market_price": None,
        "converted_raw_price": None,
        "converted_psa_7": None,
        "converted_psa_8": None,
        "converted_psa_9": None,
        "converted_psa_10": None,
    }

    history = PriceHistory(
        card_id=card_id,
        owned_card_id=owned_card_id,
        source=result.source,
        source_card_id=result.source_card_id,
        source_url=result.source_url,
        raw_price=prices.raw_price,
        market_price=prices.market_price,
        low_price=prices.low_price,
        high_price=prices.high_price,
        psa_7=prices.psa_7,
        psa_8=prices.psa_8,
        psa_9=prices.psa_9,
        psa_10=prices.psa_10,
        currency=currency,
        confidence=result.confidence,
        condition_hint=result.condition_hint,
        fetched_at=utc_now(),
        raw_response_json=json_dumps(result.raw_response),
        debug_metadata_json=json_dumps(debug_metadata),
        error_code=None if result.ok else result.error,
        error_message=None if result.ok else result.message,
        **conversion,
    )
    session.add(history)
    session.commit()
    session.refresh(history)
    if result.ok:
        create_legacy_price_observation(session, history)
    return history


def create_manual_price(session: Session, payload: ManualPriceCreate) -> PriceHistory:
    card = require_card(session, payload.card_id)
    validate_owned_card_for_card(session, payload.owned_card_id, card.id or payload.card_id)
    values = {field_name: getattr(payload, field_name) for field_name in PRICE_VALUE_FIELDS}
    validate_price_values(values)
    currency = validate_currency(payload.currency)
    result = PriceSourceResult(
        ok=True,
        source="manual",
        card_id=payload.card_id,
        source_url=payload.source_url or None,
        prices=PriceData(**values, currency=currency),
        confidence=payload.confidence or "manual",
        condition_hint=payload.condition_hint,
        raw_response={"manual": True},
        debug_metadata={"provider": "manual", "entered_by": "user"},
    )
    history = save_source_result(session, payload.card_id, payload.owned_card_id, result, duration_seconds=0.0)
    logger.info(
        "manual price stored card_id=%s owned_card_id=%s source=manual price_history_id=%s",
        payload.card_id,
        payload.owned_card_id,
        history.id,
    )
    return history


def create_legacy_price_observation(session: Session, history: PriceHistory) -> None:
    raw_price_huf = value_as_huf(history, "raw")
    market_price_huf = value_as_huf(history, "market")
    psa_7_huf = value_as_huf(history, "psa_7")
    psa_8_huf = value_as_huf(history, "psa_8")
    psa_9_huf = value_as_huf(history, "psa_9")
    psa_10_huf = value_as_huf(history, "psa_10")
    if all(value is None for value in (raw_price_huf, market_price_huf, psa_7_huf, psa_8_huf, psa_9_huf, psa_10_huf)):
        return
    observation = PriceObservation(
        card_id=history.card_id,
        owned_card_id=history.owned_card_id,
        source_name=history.source,
        currency="HUF",
        raw_price_huf=market_price_huf if market_price_huf is not None else raw_price_huf,
        psa_7_price_huf=psa_7_huf,
        psa_8_price_huf=psa_8_huf,
        psa_9_price_huf=psa_9_huf,
        psa_10_price_huf=psa_10_huf,
        price_confidence=confidence_as_float(history.confidence),
        observed_at=history.fetched_at,
        notes=history.condition_hint,
    )
    session.add(observation)
    session.commit()


def confidence_as_float(confidence: str | None) -> float | None:
    if confidence is None:
        return None
    try:
        return float(confidence)
    except ValueError:
        return {
            "manual": 1.0,
            "high": 0.85,
            "medium": 0.6,
            "low": 0.35,
        }.get(confidence.lower(), 0.5)


def value_as_huf(history: PriceHistory, price_name: str) -> float | None:
    converted_field = f"converted_{price_name}_price" if price_name in {"raw", "market"} else f"converted_{price_name}"
    converted = getattr(history, converted_field, None)
    if converted is not None:
        return converted
    if history.currency == "HUF":
        if price_name == "raw":
            return history.raw_price
        if price_name == "market":
            return history.market_price
        return getattr(history, price_name)
    return None


def latest_successful_price(
    session: Session,
    card_id: int,
    owned_card_id: int | None = None,
    at_or_before: datetime | None = None,
) -> PriceHistory | None:
    if owned_card_id is not None:
        latest_owned = latest_price_statement(session, card_id, owned_card_id, at_or_before)
        if latest_owned is not None:
            return latest_owned
    return latest_price_statement(session, card_id, None, at_or_before, include_any_owned=True)


def latest_successful_price_for_source(
    session: Session,
    card_id: int,
    source: str,
    owned_card_id: int | None = None,
) -> PriceHistory | None:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.card_id == card_id)
        .where(PriceHistory.source == source)
        .where(PriceHistory.error_code.is_(None))
    )
    if owned_card_id is not None:
        statement = statement.where(PriceHistory.owned_card_id == owned_card_id)
    else:
        statement = statement.where(PriceHistory.owned_card_id.is_(None))
    statement = statement.order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
    return session.exec(statement).first()


def latest_price_statement(
    session: Session,
    card_id: int,
    owned_card_id: int | None,
    at_or_before: datetime | None,
    include_any_owned: bool = False,
) -> PriceHistory | None:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.card_id == card_id)
        .where(PriceHistory.error_code.is_(None))
    )
    if owned_card_id is not None:
        statement = statement.where(PriceHistory.owned_card_id == owned_card_id)
    elif not include_any_owned:
        statement = statement.where(PriceHistory.owned_card_id.is_(None))
    if at_or_before is not None:
        statement = statement.where(PriceHistory.fetched_at <= at_or_before)
    statement = statement.order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
    return session.exec(statement).first()


def list_price_history(
    session: Session,
    card_id: int,
    source: str | None = None,
    currency: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> list[PriceHistory]:
    require_card(session, card_id)
    statement = select(PriceHistory).where(PriceHistory.card_id == card_id)
    if source:
        statement = statement.where(PriceHistory.source == source)
    if currency:
        statement = statement.where(PriceHistory.currency == currency.upper())
    if from_dt:
        statement = statement.where(PriceHistory.fetched_at >= from_dt)
    if to_dt:
        statement = statement.where(PriceHistory.fetched_at <= to_dt)
    statement = statement.order_by(PriceHistory.fetched_at, PriceHistory.id)
    return session.exec(statement).all()
