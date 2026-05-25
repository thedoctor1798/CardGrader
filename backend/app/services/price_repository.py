import json
import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from ..config import FX_DEFAULT_TARGET_CURRENCY, PRICE_DEFAULT_CURRENCY
from ..models import Card, OwnedCard, PriceHistory, PriceObservation
from ..models.core import utc_now
from ..schemas import ManualPriceCreate
from .fx_service import get_rate
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

SUPPORTED_CURRENCIES = {
    "AUD",
    "BGN",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "ISK",
    "JPY",
    "KRW",
    "MXN",
    "MYR",
    "NOK",
    "NZD",
    "PHP",
    "PLN",
    "RON",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "USD",
    "ZAR",
}
logger = logging.getLogger(__name__)
MARKET_PRICE_SOURCES = {"poketrace", "tcgdex", "pokemontcg", "local_json"}
ONLINE_MARKET_PRICE_SOURCES = {"poketrace", "tcgdex", "pokemontcg"}
MANUAL_PRICE_SOURCE = "manual"


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


def apply_currency_conversion(session: Session, prices: PriceData, debug_metadata: dict[str, Any]) -> dict[str, Any]:
    currency = validate_currency(prices.currency)
    target_currency = FX_DEFAULT_TARGET_CURRENCY
    if currency == target_currency:
        debug_metadata["fx"] = {
            "fx_provider": "identity",
            "fx_rate": 1.0,
            "fx_rate_date": utc_now().date().isoformat(),
            "fx_source": "identity",
            "base_currency": currency,
            "target_currency": target_currency,
        }
        return {
            "converted_currency": target_currency,
            "converted_market_price": prices.market_price,
            "converted_raw_price": prices.raw_price,
            "converted_psa_7": prices.psa_7,
            "converted_psa_8": prices.psa_8,
            "converted_psa_9": prices.psa_9,
            "converted_psa_10": prices.psa_10,
        }

    fx_rate = get_rate(session, currency, target_currency)
    if not fx_rate.ok or fx_rate.rate is None:
        debug_metadata["fx"] = {
            "fx_provider": fx_rate.provider,
            "fx_source": fx_rate.source,
            "base_currency": currency,
            "target_currency": target_currency,
            "fx_warning": fx_rate.warning or fx_rate.error or "fx_rate_unavailable",
            "message": fx_rate.message,
        }
        return {
            "converted_currency": None,
            "converted_market_price": None,
            "converted_raw_price": None,
            "converted_psa_7": None,
            "converted_psa_8": None,
            "converted_psa_9": None,
            "converted_psa_10": None,
        }

    debug_metadata["fx"] = {
        "fx_provider": fx_rate.provider,
        "fx_rate": fx_rate.rate,
        "fx_rate_date": fx_rate.rate_date.isoformat() if fx_rate.rate_date else None,
        "fx_fetched_at": fx_rate.fetched_at.isoformat() if fx_rate.fetched_at else None,
        "fx_source": fx_rate.source,
        "base_currency": currency,
        "target_currency": target_currency,
        "fx_warning": fx_rate.warning,
    }
    return {
        "converted_currency": target_currency,
        "converted_market_price": convert_price(prices.market_price, fx_rate.rate),
        "converted_raw_price": convert_price(prices.raw_price, fx_rate.rate),
        "converted_psa_7": convert_price(prices.psa_7, fx_rate.rate),
        "converted_psa_8": convert_price(prices.psa_8, fx_rate.rate),
        "converted_psa_9": convert_price(prices.psa_9, fx_rate.rate),
        "converted_psa_10": convert_price(prices.psa_10, fx_rate.rate),
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
    conversion = apply_currency_conversion(session, prices, debug_metadata) if result.ok else {
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


def price_kind_for(history: PriceHistory | None, fallback: bool = False) -> str | None:
    if history is None:
        return None
    source = (history.source or "").lower()
    if fallback and source == MANUAL_PRICE_SOURCE:
        return "manual_fallback"
    if source == MANUAL_PRICE_SOURCE:
        return "manual_owned" if history.owned_card_id is not None else "manual_card"
    if source in ONLINE_MARKET_PRICE_SOURCES:
        return "market_online"
    if source == "local_json":
        return "local_json"
    return "unknown"


def price_scope_for(history: PriceHistory | None, requested_owned_card_id: int | None = None) -> str | None:
    if history is None:
        return None
    if history.owned_card_id is not None:
        return "owned_card"
    if requested_owned_card_id is not None:
        return "fallback_card"
    return "card"


def annotate_price_history(
    history: PriceHistory | None,
    requested_owned_card_id: int | None = None,
    price_scope: str | None = None,
    price_kind: str | None = None,
    manual_fallback: bool = False,
) -> PriceHistory | None:
    if history is None:
        return None
    setattr(history, "price_scope", price_scope or price_scope_for(history, requested_owned_card_id))
    setattr(history, "price_kind", price_kind or price_kind_for(history, fallback=manual_fallback))
    return history


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


def latest_market_price(
    session: Session,
    card_id: int,
    owned_card_id: int | None = None,
    at_or_before: datetime | None = None,
) -> PriceHistory | None:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.card_id == card_id)
        .where(PriceHistory.source.in_(list(MARKET_PRICE_SOURCES)))
        .where(PriceHistory.error_code.is_(None))
    )
    if owned_card_id is not None:
        statement = statement.where(or_(PriceHistory.owned_card_id == owned_card_id, PriceHistory.owned_card_id.is_(None)))
    else:
        statement = statement.where(PriceHistory.owned_card_id.is_(None))
    if at_or_before is not None:
        statement = statement.where(PriceHistory.fetched_at <= at_or_before)
    statement = statement.order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
    return session.exec(statement).first()


def latest_manual_price(
    session: Session,
    card_id: int,
    owned_card_id: int | None = None,
    at_or_before: datetime | None = None,
) -> PriceHistory | None:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.card_id == card_id)
        .where(PriceHistory.source == MANUAL_PRICE_SOURCE)
        .where(PriceHistory.error_code.is_(None))
    )
    if owned_card_id is not None:
        statement = statement.where(PriceHistory.owned_card_id == owned_card_id)
    else:
        statement = statement.where(PriceHistory.owned_card_id.is_(None))
    if at_or_before is not None:
        statement = statement.where(PriceHistory.fetched_at <= at_or_before)
    statement = statement.order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
    return session.exec(statement).first()


def latest_market_with_manual_fallback(
    session: Session,
    card_id: int,
    owned_card_id: int | None = None,
    at_or_before: datetime | None = None,
) -> tuple[PriceHistory | None, bool]:
    market = latest_market_price(session, card_id, owned_card_id, at_or_before)
    if market is not None:
        return market, False
    manual_owned = latest_manual_price(session, card_id, owned_card_id, at_or_before) if owned_card_id is not None else None
    if manual_owned is not None:
        return manual_owned, True
    manual_card = latest_manual_price(session, card_id, None, at_or_before)
    if manual_card is not None:
        return manual_card, True
    return None, False


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
    history = session.exec(statement).all()
    for item in history:
        annotate_price_history(item)
    return history
