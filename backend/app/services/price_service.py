import logging
import time
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import PRICE_FETCH_ENABLED, PRICE_RATE_LIMIT_SECONDS, PRICE_SOURCES
from ..models import Card, OwnedCard, PriceHistory
from ..schemas import PriceFetchRequest, PriceFetchResponse, PriceFetchResultRead, PriceProvidersStatusResponse, PriceRefreshResponse
from .price_repository import (
    latest_successful_price_for_source,
    latest_successful_price,
    require_card,
    save_source_result,
    validate_owned_card_for_card,
)
from .price_sources import (
    LocalJsonPriceSource,
    ManualPriceSource,
    PokemonTCGPriceSource,
    PokeTracePriceSource,
    PriceSource,
    PriceSourceResult,
    TCGdexPriceSource,
)
from .provider_rate_limiter import block_provider, provider_blocked_seconds, wait_for_provider_slot
from .provider_settings import effective_provider_config, list_safe_provider_settings

logger = logging.getLogger(__name__)
ONLINE_PRICE_SOURCES = {"poketrace", "tcgdex", "pokemontcg"}


def provider_for_source(session: Session, source_name: str) -> PriceSource | None:
    normalized = source_name.strip().lower()
    if normalized == "manual":
        return ManualPriceSource()
    if normalized == "local_json":
        return LocalJsonPriceSource()
    effective = effective_provider_config(session, normalized) if normalized in ONLINE_PRICE_SOURCES else None
    if normalized == "poketrace" and effective is not None:
        return PokeTracePriceSource(effective)
    if normalized == "tcgdex" and effective is not None:
        return TCGdexPriceSource(effective)
    if normalized == "pokemontcg" and effective is not None:
        return PokemonTCGPriceSource(effective)
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
    explicit_sources = request.sources is not None
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
        provider = provider_for_source(session, source_name)
        if provider is None:
            result = PriceSourceResult(
                ok=False,
                source=source_name,
                card_id=card_id,
                error="price_source_not_configured",
                message=f"Price source '{source_name}' is not configured.",
                debug_metadata={"provider": source_name},
            )
        elif source_name in ONLINE_PRICE_SOURCES and should_skip_disabled_provider(session, source_name, explicit_sources):
            result_read = PriceFetchResultRead(
                ok=False,
                source=source_name,
                skipped=True,
                error="price_source_disabled",
                message=f"Price source '{source_name}' is disabled.",
                duration_seconds=round(time.monotonic() - started, 4),
            )
            results.append(result_read)
            if explicit_sources:
                failed_count += 1
            continue
        elif source_name in ONLINE_PRICE_SOURCES and not request.force:
            cached = cached_source_price(session, card_id, source_name, request.owned_card_id)
            if cached is not None:
                latest_price = cached
                results.append(
                    PriceFetchResultRead(
                        ok=True,
                        source=source_name,
                        price_history_id=cached.id,
                        source_card_id=cached.source_card_id,
                        source_url=cached.source_url,
                        skipped=True,
                        message="Using cached provider price data.",
                        duration_seconds=round(time.monotonic() - started, 4),
                    )
                )
                continue
            result = run_provider_with_rate_limit(session, source_name, provider, card, request.owned_card_id)
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
            maybe_block_rate_limited_provider(source_name, result)
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
                skipped=result.skipped,
                match_score=result.match_score,
                rate_limit_remaining=result.rate_limit_remaining,
                warning=result.warning,
            )
        )

    latest_price = latest_price or latest_successful_price(session, card_id, request.owned_card_id)
    if fetched_count == 0 and latest_price is not None and any(result.skipped and result.ok for result in results):
        return PriceFetchResponse(
            ok=True,
            card_id=card_id,
            fetched_count=fetched_count,
            failed_count=failed_count,
            latest_price=latest_price,
            results=results,
            message="Using cached price data.",
        )
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
    sources = configured_sources()
    original_card_count = len(card_ids)
    message = None
    card_ids = conservative_refresh_subset(session, card_ids, sources)
    if len(card_ids) < original_card_count:
        message = f"Refresh limited to {len(card_ids)} cards for the configured provider plan."
    if len(card_ids) == 0:
        message = "No cards selected for refresh."
    should_sleep = should_rate_limit(sources)
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
        message=message,
    )


def should_rate_limit(sources: list[str]) -> bool:
    return any(source not in {"manual", "local_json"} for source in sources)


def conservative_refresh_subset(session: Session, card_ids: list[int], sources: list[str]) -> list[int]:
    if "poketrace" not in sources:
        return card_ids
    effective = effective_provider_config(session, "poketrace")
    if effective.config.get("plan") != "free":
        return card_ids
    daily_limit = int(effective.config.get("daily_limit") or 250)
    if len(card_ids) <= daily_limit:
        return card_ids
    logger.warning(
        "price refresh trimmed for poketrace free plan card_count=%s daily_limit=%s",
        len(card_ids),
        daily_limit,
    )
    return card_ids[:daily_limit]


def price_provider_statuses(session: Session) -> PriceProvidersStatusResponse:
    return PriceProvidersStatusResponse(ok=True, providers=list_safe_provider_settings(session))


def should_skip_disabled_provider(session: Session, source_name: str, explicit_sources: bool) -> bool:
    effective = effective_provider_config(session, source_name)
    return not effective.enabled and not explicit_sources


def cached_source_price(
    session: Session,
    card_id: int,
    source_name: str,
    owned_card_id: int | None,
) -> PriceHistory | None:
    effective = effective_provider_config(session, source_name)
    ttl_hours = float(effective.config.get("cache_ttl_hours") or 0)
    if ttl_hours <= 0:
        return None
    latest = latest_successful_price_for_source(session, card_id, source_name, owned_card_id)
    if latest is None:
        return None
    if latest.fetched_at >= datetime.utcnow() - timedelta(hours=ttl_hours):
        return latest
    return None


def run_provider_with_rate_limit(
    session: Session,
    source_name: str,
    provider: PriceSource,
    card: Card,
    owned_card_id: int | None,
) -> PriceSourceResult:
    blocked = provider_blocked_seconds(source_name)
    if blocked > 0:
        return PriceSourceResult(
            ok=False,
            source=source_name,
            card_id=card.id or 0,
            skipped=True,
            warning="provider_rate_limited",
            error="provider_rate_limited",
            message=f"Provider is rate limited. Try again in {int(blocked)} seconds.",
            debug_metadata={"provider": source_name, "blocked_seconds": round(blocked, 2)},
        )
    wait_for_provider_slot(source_name, provider_rate_limit_interval(session, source_name))
    try:
        return provider.fetch(session, card, owned_card_id)
    except TimeoutError as exc:
        return PriceSourceResult(
            ok=False,
            source=source_name,
            card_id=card.id or 0,
            error="provider_timeout",
            message=str(exc) or "Price provider timed out.",
            debug_metadata={"provider": source_name},
        )
    except Exception as exc:  # noqa: BLE001 - provider boundary converts to structured error
        logger.exception("price provider failed source=%s card_id=%s", source_name, card.id)
        return PriceSourceResult(
            ok=False,
            source=source_name,
            card_id=card.id or 0,
            error="provider_error",
            message="Price provider failed.",
            debug_metadata={"provider": source_name, "error": str(exc)},
        )


def provider_rate_limit_interval(session: Session, source_name: str) -> float:
    effective = effective_provider_config(session, source_name)
    if source_name == "poketrace":
        burst_limit = max(1, int(effective.config.get("burst_limit") or 1))
        burst_window = float(effective.config.get("burst_window_seconds") or 2)
        return max(2.0 if effective.config.get("plan") == "free" else 0.0, burst_window / burst_limit)
    if source_name in {"tcgdex", "pokemontcg"}:
        return float(effective.config.get("rate_limit_seconds") or 2)
    return PRICE_RATE_LIMIT_SECONDS


def maybe_block_rate_limited_provider(source_name: str, result: PriceSourceResult) -> None:
    if result.error != "provider_rate_limited":
        return
    retry_after = None
    rate_limit = result.debug_metadata.get("rate_limit") if isinstance(result.debug_metadata, dict) else None
    if isinstance(rate_limit, dict):
        try:
            retry_after = int(rate_limit.get("Retry-After"))
        except (TypeError, ValueError):
            retry_after = None
    if retry_after is None:
        retry_after = result.debug_metadata.get("retry_after") if isinstance(result.debug_metadata, dict) else None
    try:
        block_provider(source_name, float(retry_after))
    except (TypeError, ValueError):
        pass
