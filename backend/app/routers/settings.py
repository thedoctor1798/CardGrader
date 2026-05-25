from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import (
    PriceProviderSettingResponse,
    PriceProviderSettingsResponse,
    PriceProviderSettingsUpdate,
    PriceProviderTestResponse,
)
from ..services.provider_settings import (
    effective_provider_config,
    list_safe_provider_settings,
    normalize_provider,
    save_provider_setting,
)
from ..services.price_sources.common import ProviderHttpError, build_url, get_json, int_header, rate_limit_headers

router = APIRouter()


@router.get("/settings/price-providers", response_model=PriceProviderSettingsResponse)
def get_price_provider_settings(session: Session = Depends(get_session)):
    return PriceProviderSettingsResponse(ok=True, providers=list_safe_provider_settings(session))


@router.put("/settings/price-providers/{provider}", response_model=PriceProviderSettingResponse)
def update_price_provider_setting(
    provider: str,
    payload: PriceProviderSettingsUpdate,
    session: Session = Depends(get_session),
):
    normalized = normalize_provider(provider)
    saved = save_provider_setting(session, normalized, payload.dict(exclude_unset=True))
    return PriceProviderSettingResponse(ok=True, provider=saved)


@router.post("/settings/price-providers/{provider}/test", response_model=PriceProviderTestResponse)
def test_price_provider_setting(provider: str, session: Session = Depends(get_session)):
    normalized = normalize_provider(provider)
    effective = effective_provider_config(session, normalized)
    if not effective.enabled:
        return PriceProviderTestResponse(
            ok=False,
            provider=normalized,
            configured=effective.configured,
            plan=effective.config.get("plan"),
            error="price_source_disabled",
            message="Provider is disabled.",
        )
    if not effective.configured:
        return PriceProviderTestResponse(
            ok=False,
            provider=normalized,
            configured=False,
            plan=effective.config.get("plan"),
            error="price_source_not_configured",
            message="Provider is missing required configuration.",
        )

    if normalized == "poketrace":
        return test_poketrace(effective)
    if normalized == "tcgdex":
        return test_public_get(
            normalized,
            build_url(effective.config["base_url"], "/en/cards", {"pagination:page": 1, "pagination:itemsPerPage": 1}),
            int(effective.config["timeout_seconds"]),
        )
    if normalized == "pokemontcg":
        headers = {"Accept": "application/json"}
        if effective.secrets.get("api_key"):
            headers["X-Api-Key"] = str(effective.secrets["api_key"])
        return test_public_get(
            normalized,
            build_url(effective.config["base_url"], "/cards", {"page": 1, "pageSize": 1}),
            int(effective.config["timeout_seconds"]),
            headers=headers,
        )
    return PriceProviderTestResponse(
        ok=True,
        provider=normalized,
        configured=True,
        message="Provider does not require an external connection test.",
    )


def test_poketrace(effective) -> PriceProviderTestResponse:
    headers = {"X-API-Key": str(effective.secrets.get("api_key") or ""), "Accept": "application/json"}
    url = build_url(effective.config["base_url"], "/auth/info")
    try:
        response = get_json(url, headers=headers, timeout=int(effective.config["timeout_seconds"]))
    except ProviderHttpError as exc:
        if exc.status_code in {401, 403}:
            return PriceProviderTestResponse(
                ok=False,
                provider="poketrace",
                configured=True,
                plan=effective.config.get("plan"),
                error="provider_auth_failed",
                message="PokeTrace API key was rejected.",
            )
        return PriceProviderTestResponse(
            ok=False,
            provider="poketrace",
            configured=True,
            plan=effective.config.get("plan"),
            error="provider_error",
            message=str(exc),
        )
    headers_payload = rate_limit_headers(response.headers)
    if response.status_code == 429:
        return PriceProviderTestResponse(
            ok=False,
            provider="poketrace",
            configured=True,
            plan=effective.config.get("plan"),
            rate_limit=headers_payload,
            rate_limit_remaining=int_header(headers_payload, "X-RateLimit-Remaining"),
            error="provider_rate_limited",
            message="PokeTrace rate limit reached. Try again later.",
        )
    return PriceProviderTestResponse(
        ok=True,
        provider="poketrace",
        configured=True,
        plan=headers_payload.get("X-Plan") or effective.config.get("plan"),
        rate_limit=headers_payload,
        rate_limit_remaining=int_header(headers_payload, "X-RateLimit-Remaining"),
        message="PokeTrace connection OK.",
    )


def test_public_get(
    provider: str,
    url: str,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
) -> PriceProviderTestResponse:
    try:
        response = get_json(url, headers=headers or {"Accept": "application/json"}, timeout=timeout_seconds)
    except ProviderHttpError as exc:
        if exc.status_code in {401, 403}:
            return PriceProviderTestResponse(
                ok=False,
                provider=provider,
                configured=True,
                error="provider_auth_failed",
                message=f"{provider} authentication failed.",
            )
        return PriceProviderTestResponse(
            ok=False,
            provider=provider,
            configured=True,
            error="provider_error",
            message=str(exc),
        )
    if response.status_code == 429:
        return PriceProviderTestResponse(
            ok=False,
            provider=provider,
            configured=True,
            error="provider_rate_limited",
            message=f"{provider} rate limit reached.",
        )
    return PriceProviderTestResponse(ok=True, provider=provider, configured=True, message=f"{provider} connection OK.")
