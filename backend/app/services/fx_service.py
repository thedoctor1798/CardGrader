import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from .. import config
from ..models import FxRate
from ..models.core import utc_now
from .price_sources.common import build_url

logger = logging.getLogger(__name__)


@dataclass
class FxRateResult:
    ok: bool
    base_currency: str
    target_currency: str
    rate: float | None = None
    rate_date: date | None = None
    fetched_at: datetime | None = None
    expires_at: datetime | None = None
    provider: str = config.FX_PROVIDER
    source: str | None = None
    raw_response: Any = None
    warning: str | None = None
    error: str | None = None
    message: str | None = None
    requested_url: str | None = None
    http_status: int | None = None
    response_content_type: str | None = None
    response_preview: str | None = None


def get_rate(
    session: Session,
    base_currency: str,
    target_currency: str | None = None,
    force: bool = False,
) -> FxRateResult:
    base = normalize_currency(base_currency)
    target = normalize_currency(target_currency or config.FX_DEFAULT_TARGET_CURRENCY)
    if base == target:
        now = utc_now()
        return FxRateResult(
            ok=True,
            base_currency=base,
            target_currency=target,
            rate=1.0,
            rate_date=now.date(),
            fetched_at=now,
            expires_at=now,
            source="identity",
        )

    cached = latest_cached_rate(session, base, target)
    if cached is not None and not force and cached.expires_at > utc_now():
        cached_debug = fx_debug_from_raw_response(cached.raw_response_json)
        return FxRateResult(
            ok=True,
            base_currency=base,
            target_currency=target,
            rate=cached.rate,
            rate_date=cached.rate_date,
            fetched_at=cached.fetched_at,
            expires_at=cached.expires_at,
            provider=cached.provider,
            source="cache",
            raw_response=parse_json(cached.raw_response_json),
            requested_url=cached_debug.get("requested_url"),
            http_status=cached_debug.get("http_status"),
            response_content_type=cached_debug.get("response_content_type"),
            response_preview=cached_debug.get("response_preview"),
        )

    if not config.FX_CONVERSION_ENABLED:
        static = static_rate(base, target, "fx_conversion_disabled")
        return static or FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            source="disabled",
            warning="fx_conversion_disabled",
            error="fx_conversion_disabled",
            message="FX conversion is disabled.",
        )

    provider_result = fetch_provider_rate(base, target)
    if provider_result.ok and provider_result.rate is not None:
        stored = save_fx_rate(session, provider_result)
        stored_debug = fx_debug_from_raw_response(stored.raw_response_json)
        return FxRateResult(
            ok=True,
            base_currency=base,
            target_currency=target,
            rate=stored.rate,
            rate_date=stored.rate_date,
            fetched_at=stored.fetched_at,
            expires_at=stored.expires_at,
            provider=stored.provider,
            source=provider_result.source,
            raw_response=parse_json(stored.raw_response_json),
            requested_url=stored_debug.get("requested_url"),
            http_status=stored_debug.get("http_status"),
            response_content_type=stored_debug.get("response_content_type"),
            response_preview=stored_debug.get("response_preview"),
        )

    static = static_rate(base, target, provider_result.warning or provider_result.error)
    if static is not None:
        return static
    if cached is not None:
        cached_debug = fx_debug_from_raw_response(cached.raw_response_json)
        return FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            rate=None,
            rate_date=cached.rate_date,
            fetched_at=cached.fetched_at,
            expires_at=cached.expires_at,
            provider=cached.provider,
            source="stale_cache",
            raw_response=parse_json(cached.raw_response_json),
            warning="fx_provider_failed_stale_cache_available",
            error=provider_result.error,
            message=provider_result.message,
            requested_url=cached_debug.get("requested_url"),
            http_status=cached_debug.get("http_status"),
            response_content_type=cached_debug.get("response_content_type"),
            response_preview=cached_debug.get("response_preview"),
        )
    return provider_result


def refresh_rates(
    session: Session,
    currencies: list[str] | None = None,
    target_currency: str | None = None,
    force: bool = True,
) -> list[FxRateResult]:
    target = normalize_currency(target_currency or config.FX_DEFAULT_TARGET_CURRENCY)
    requested = currencies or ["USD", "EUR"]
    return [get_rate(session, currency, target, force=force) for currency in requested]


def list_cached_rates(session: Session) -> list[FxRate]:
    statement = select(FxRate).order_by(FxRate.base_currency, FxRate.target_currency, FxRate.rate_date.desc())
    return session.exec(statement).all()


def latest_fx_refresh_at(session: Session) -> datetime | None:
    latest = session.exec(select(FxRate).order_by(FxRate.fetched_at.desc(), FxRate.id.desc())).first()
    return latest.fetched_at if latest is not None else None


def latest_cached_rate(session: Session, base: str, target: str) -> FxRate | None:
    statement = (
        select(FxRate)
        .where(FxRate.provider == config.FX_PROVIDER)
        .where(FxRate.base_currency == base)
        .where(FxRate.target_currency == target)
        .order_by(FxRate.rate_date.desc(), FxRate.fetched_at.desc(), FxRate.id.desc())
    )
    return session.exec(statement).first()


def fetch_provider_rate(base: str, target: str) -> FxRateResult:
    if config.FX_PROVIDER != "frankfurter":
        return FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            source=config.FX_PROVIDER,
            warning="fx_provider_not_supported",
            error="fx_provider_not_supported",
            message=f"FX provider is not supported: {config.FX_PROVIDER}",
        )

    response = fetch_frankfurter_rate(base, target)
    if not response.ok:
        return response

    rate, rate_date = parse_frankfurter_response(response.raw_response, target)
    if rate is None or rate <= 0:
        return FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            source=response.source,
            warning="fx_rate_missing",
            error="fx_rate_missing",
            message="Frankfurter response did not include the requested rate.",
            raw_response=response.raw_response,
            requested_url=response.requested_url,
            http_status=response.http_status,
            response_content_type=response.response_content_type,
            response_preview=response.response_preview,
        )

    now = utc_now()
    return FxRateResult(
        ok=True,
        base_currency=base,
        target_currency=target,
        rate=rate,
        rate_date=rate_date or now.date(),
        fetched_at=now,
        expires_at=now + timedelta(hours=config.FX_CACHE_TTL_HOURS),
        provider="frankfurter",
        source=response.source,
        raw_response=response.raw_response,
        requested_url=response.requested_url,
        http_status=response.http_status,
        response_content_type=response.response_content_type,
        response_preview=response.response_preview,
    )


def fetch_frankfurter_rate(base: str, target: str) -> FxRateResult:
    attempts = [
        ("frankfurter_v2", frankfurter_v2_url(base, target)),
        ("frankfurter_v1", frankfurter_v1_url(base, target)),
    ]
    last_error: FxRateResult | None = None
    for source, url in attempts:
        result = request_frankfurter_json(url, source, base, target)
        if result.ok:
            return result
        last_error = result
        if result.error == "fx_provider_timeout":
            continue
        if result.error in {"fx_provider_blocked", "fx_provider_blocked_or_incompatible"}:
            continue
    return last_error or FxRateResult(
        ok=False,
        base_currency=base,
        target_currency=target,
        source="frankfurter",
        warning="fx_provider_failed",
        error="fx_provider_failed",
        message="Frankfurter FX request failed.",
    )


def request_frankfurter_json(url: str, source: str, base: str, target: str) -> FxRateResult:
    headers = {
        "Accept": "application/json",
        "User-Agent": config.FX_USER_AGENT,
    }
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=config.FX_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                return blocked_or_incompatible_result(base, target, source, url, response.status, content_type, body)
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                return blocked_or_incompatible_result(base, target, source, url, response.status, content_type, body)
            if "1010" in body:
                return blocked_or_incompatible_result(base, target, source, url, response.status, content_type, body)
            return FxRateResult(
                ok=True,
                base_currency=base,
                target_currency=target,
                source=source,
                provider="frankfurter",
                raw_response=payload,
                requested_url=url,
                http_status=response.status,
                response_content_type=content_type,
                response_preview=body[:500],
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("Content-Type", "")
        if exc.code == 403 or "1010" in body or "html" in content_type.lower():
            return blocked_or_incompatible_result(base, target, source, url, exc.code, content_type, body)
        return FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            source=source,
            warning="fx_provider_failed",
            error="fx_provider_failed",
            message=f"Frankfurter returned HTTP {exc.code}.",
            requested_url=url,
            http_status=exc.code,
            response_content_type=content_type,
            response_preview=body[:500],
        )
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        return FxRateResult(
            ok=False,
            base_currency=base,
            target_currency=target,
            source=source,
            warning="fx_provider_timeout",
            error="fx_provider_timeout",
            message=reason or "Frankfurter FX request timed out.",
            requested_url=url,
        )


def blocked_or_incompatible_result(
    base: str,
    target: str,
    source: str,
    url: str,
    status: int | None,
    content_type: str | None,
    body: str,
) -> FxRateResult:
    return FxRateResult(
        ok=False,
        base_currency=base,
        target_currency=target,
        source=source,
        warning="fx_provider_blocked",
        error="fx_provider_blocked",
        message="Frankfurter blocked the request. Try setting FX_USER_AGENT or use static FX fallback.",
        requested_url=url,
        http_status=status,
        response_content_type=content_type,
        response_preview=body[:500],
    )


def frankfurter_v2_url(base: str, target: str) -> str:
    return build_url(config.FX_PROVIDER_BASE_URL, "/rates", {"base": base, "quotes": target})


def frankfurter_v1_url(base: str, target: str) -> str:
    return build_url(config.FX_PROVIDER_FALLBACK_BASE_URL, "/latest", {"base": base, "symbols": target})


def parse_frankfurter_response(payload: Any, target: str) -> tuple[float | None, date | None]:
    if isinstance(payload, dict):
        rates = payload.get("rates")
        if isinstance(rates, dict):
            return optional_float(rates.get(target)), parse_date(payload.get("date"))
        data = payload.get("data")
        if isinstance(data, list) and data:
            return parse_frankfurter_response(data[0], target)
        if "rate" in payload:
            return optional_float(payload.get("rate")), parse_date(payload.get("date"))
    if isinstance(payload, list) and payload:
        return parse_frankfurter_response(payload[0], target)
    return None, None


def save_fx_rate(session: Session, result: FxRateResult) -> FxRate:
    rate_date = result.rate_date or utc_now().date()
    existing = session.exec(
        select(FxRate)
        .where(FxRate.provider == result.provider)
        .where(FxRate.base_currency == result.base_currency)
        .where(FxRate.target_currency == result.target_currency)
        .where(FxRate.rate_date == rate_date)
    ).first()
    now = result.fetched_at or utc_now()
    rate = existing or FxRate(
        provider=result.provider,
        base_currency=result.base_currency,
        target_currency=result.target_currency,
        rate_date=rate_date,
    )
    rate.rate = float(result.rate or 0)
    rate.fetched_at = now
    rate.expires_at = result.expires_at or now + timedelta(hours=config.FX_CACHE_TTL_HOURS)
    raw_payload = {
        "response": result.raw_response,
        "requested_url": result.requested_url,
        "http_status": result.http_status,
        "response_content_type": result.response_content_type,
        "response_preview": result.response_preview,
        "source": result.source,
    }
    rate.raw_response_json = json.dumps(raw_payload, ensure_ascii=True, default=str)
    rate.error_code = result.error
    rate.error_message = result.message
    rate.updated_at = now
    session.add(rate)
    session.commit()
    session.refresh(rate)
    return rate


def static_rate(base: str, target: str, warning: str | None = None) -> FxRateResult | None:
    if not config.FX_FALLBACK_TO_STATIC_RATES or target != "HUF":
        return None
    rate = {"EUR": config.PRICE_FX_EUR_HUF, "USD": config.PRICE_FX_USD_HUF}.get(base)
    if rate is None:
        return None
    now = utc_now()
    return FxRateResult(
        ok=True,
        base_currency=base,
        target_currency=target,
        rate=rate,
        rate_date=now.date(),
        fetched_at=now,
        expires_at=now,
        provider="static",
        source="static",
        warning=warning,
        message="Frankfurter failed, using configured static FX fallback." if warning else None,
    )


def normalize_currency(currency: str | None) -> str:
    return (currency or config.FX_DEFAULT_TARGET_CURRENCY).strip().upper()


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def fx_debug_from_raw_response(value: str | None) -> dict[str, Any]:
    parsed = parse_json(value)
    if not isinstance(parsed, dict):
        return {}
    return {
        "requested_url": parsed.get("requested_url"),
        "http_status": parsed.get("http_status"),
        "response_content_type": parsed.get("response_content_type"),
        "response_preview": parsed.get("response_preview"),
    }
