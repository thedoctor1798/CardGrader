import logging
import time
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import PRICE_FETCH_ENABLED, PRICE_RATE_LIMIT_SECONDS, PRICE_SOURCES
from ..models import Card, OwnedCard, PriceHistory
from ..schemas import PriceFetchRequest, PriceFetchResponse, PriceFetchResultRead, PriceRefreshResponse
from .price_repository import (
    latest_successful_price,
    require_card,
    save_source_result,
    validate_owned_card_for_card,
)
from .price_sources import LocalJsonPriceSource, ManualPriceSource, PriceSource, PriceSourceResult

logger = logging.getLogger(__name__)


def provider_for_source(source_name: str) -> PriceSource | None:
    normalized = source_name.strip().lower()
    if normalized == "manual":
        return ManualPriceSource()
    if normalized == "local_json":
        return LocalJsonPriceSource()
    return None


def configured_sources(requested_sources: list[str] | None = None) -> list[str]:
    source_names = requested_sources if requested_sources is not None else PRICE_SOURCES
    return [source.strip().lower() for source in source_names if source and source.strip()]


def fetch_prices_for_card(
    session: Session,
    card_id: int,
    request: PriceFetchRequest | None = None,
) -> PriceFetchResponse:
    if not PRICE_FETCH_ENABLED:
        return PriceFetchResponse(
            ok=False,
            card_id=card_id,
            fetched_count=0,
            failed_count=0,
            latest_price=None,
            results=[],
            error="price_fetch_disabled",
            message="Price fetching is disabled by PRICE_FETCH_ENABLED=false.",
        )

    request = request or PriceFetchRequest()
    card = require_card(session, card_id)
    validate_owned_card_for_card(session, request.owned_card_id, card.id or card_id)
    sources = configured_sources(request.sources)
    if not sources:
        return PriceFetchResponse(
            ok=False,
            card_id=card_id,
            fetched_count=0,
            failed_count=0,
            latest_price=None,
            results=[],
            error="no_price_source_configured",
            message="No configured price source is available for this card.",
        )

    results: list[PriceFetchResultRead] = []
    fetched_count = 0
    failed_count = 0
    latest_price: PriceHistory | None = None

    logger.info(
        "price fetch requested card_id=%s owned_card_id=%s sources=%s",
        card_id,
        request.owned_card_id,
        ",".join(sources),
    )

    for source_name in sources:
        started = time.monotonic()
        provider = provider_for_source(source_name)
        if provider is None:
            result = PriceSourceResult(
                ok=False,
                source=source_name,
                card_id=card_id,
                error="price_source_not_configured",
                message=f"Price source '{source_name}' is not configured.",
                debug_metadata={"provider": source_name},
            )
        else:
            try:
                result = provider.fetch(session, card, request.owned_card_id)
            except TimeoutError as exc:
                result = PriceSourceResult(
                    ok=False,
                    source=source_name,
                    card_id=card_id,
                    error="provider_timeout",
                    message=str(exc) or "Price provider timed out.",
                    debug_metadata={"provider": source_name},
                )
            except Exception as exc:  # noqa: BLE001 - provider boundary converts to structured error
                logger.exception("price provider failed source=%s card_id=%s", source_name, card_id)
                result = PriceSourceResult(
                    ok=False,
                    source=source_name,
                    card_id=card_id,
                    error="provider_error",
                    message="Price provider failed.",
                    debug_metadata={"provider": source_name, "error": str(exc)},
                )

        duration = round(time.monotonic() - started, 4)
        if result.ok and (result.prices is None or not result.prices.has_any_price()):
            result.ok = False
            result.error = "invalid_provider_response"
            result.message = "Price provider did not return usable price data."

        try:
            stored = save_source_result(session, card_id, request.owned_card_id, result, duration)
        except HTTPException as exc:
            result = PriceSourceResult(
                ok=False,
                source=source_name,
                card_id=card_id,
                error="invalid_provider_response",
                message=str(exc.detail),
                debug_metadata={"provider": source_name, "error": exc.detail},
            )
            stored = save_source_result(session, card_id, request.owned_card_id, result, duration)

        if result.ok:
            fetched_count += 1
            latest_price = stored
            logger.info(
                "price fetch success card_id=%s owned_card_id=%s source=%s duration=%s price_history_id=%s",
                card_id,
                request.owned_card_id,
                source_name,
                duration,
                stored.id,
            )
        else:
            failed_count += 1
            logger.info(
                "price fetch failure card_id=%s owned_card_id=%s source=%s duration=%s error=%s price_history_id=%s",
                card_id,
                request.owned_card_id,
                source_name,
                duration,
                result.error,
                stored.id,
            )

        results.append(
            PriceFetchResultRead(
                ok=result.ok,
                source=source_name,
                price_history_id=stored.id,
                source_card_id=result.source_card_id,
                source_url=result.source_url,
                error=result.error,
                message=result.message,
                duration_seconds=duration,
            )
        )

    latest_price = latest_price or latest_successful_price(session, card_id, request.owned_card_id)
    if fetched_count == 0:
        return PriceFetchResponse(
            ok=False,
            card_id=card_id,
            fetched_count=fetched_count,
            failed_count=failed_count,
            latest_price=latest_price,
            results=results,
            error="all_price_sources_failed",
            message="No price source returned usable price data.",
        )

    return PriceFetchResponse(
        ok=True,
        card_id=card_id,
        fetched_count=fetched_count,
        failed_count=failed_count,
        latest_price=latest_price,
        results=results,
    )


def refresh_prices(session: Session, owned_only: bool) -> PriceRefreshResponse:
    started_at = datetime.utcnow()
    if owned_only:
        owned_cards = session.exec(select(OwnedCard).order_by(OwnedCard.card_id)).all()
        card_ids = sorted({owned_card.card_id for owned_card in owned_cards})
    else:
        card_ids = [card.id for card in session.exec(select(Card).order_by(Card.id)).all() if card.id is not None]

    success_count = 0
    failure_count = 0
    should_sleep = should_rate_limit(configured_sources())
    for index, card_id in enumerate(card_ids):
        response = fetch_prices_for_card(session, card_id, PriceFetchRequest())
        if response.ok:
            success_count += 1
        else:
            failure_count += 1
        if should_sleep and index < len(card_ids) - 1 and PRICE_RATE_LIMIT_SECONDS > 0:
            time.sleep(PRICE_RATE_LIMIT_SECONDS)

    finished_at = datetime.utcnow()
    logger.info(
        "price refresh summary owned_only=%s cards_checked=%s success_count=%s failure_count=%s",
        owned_only,
        len(card_ids),
        success_count,
        failure_count,
    )
    return PriceRefreshResponse(
        ok=True,
        cards_checked=len(card_ids),
        success_count=success_count,
        failure_count=failure_count,
        started_at=started_at,
        finished_at=finished_at,
    )


def should_rate_limit(sources: list[str]) -> bool:
    return any(source not in {"manual", "local_json"} for source in sources)
