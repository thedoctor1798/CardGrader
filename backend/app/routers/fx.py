from fastapi import APIRouter, Depends
from sqlmodel import Session

from .. import config
from ..database import get_session
from ..schemas import FxRateRead, FxRatesResponse, FxRefreshRequest
from ..services.fx_service import FxRateResult, refresh_rates

router = APIRouter()


@router.get("/fx/rates", response_model=FxRatesResponse)
def get_fx_rates(session: Session = Depends(get_session)):
    rates = refresh_rates(session, currencies=["USD", "EUR"], target_currency=config.FX_DEFAULT_TARGET_CURRENCY, force=False)
    return FxRatesResponse(
        ok=True,
        enabled=config.FX_CONVERSION_ENABLED,
        provider=config.FX_PROVIDER,
        target_currency=config.FX_DEFAULT_TARGET_CURRENCY,
        cache_ttl_hours=config.FX_CACHE_TTL_HOURS,
        rates=[fx_result_to_read(rate) for rate in rates],
    )


@router.post("/fx/refresh", response_model=FxRatesResponse)
def refresh_fx_rates(payload: FxRefreshRequest, session: Session = Depends(get_session)):
    rates = refresh_rates(
        session,
        currencies=payload.currencies,
        target_currency=payload.target_currency,
        force=payload.force,
    )
    return FxRatesResponse(
        ok=all(rate.ok for rate in rates),
        enabled=config.FX_CONVERSION_ENABLED,
        provider=config.FX_PROVIDER,
        target_currency=payload.target_currency.upper(),
        cache_ttl_hours=config.FX_CACHE_TTL_HOURS,
        rates=[fx_result_to_read(rate) for rate in rates],
    )


def fx_result_to_read(result: FxRateResult) -> FxRateRead:
    return FxRateRead(
        base_currency=result.base_currency,
        target_currency=result.target_currency,
        rate=result.rate,
        rate_date=result.rate_date,
        source=result.source,
        provider=result.provider,
        fetched_at=result.fetched_at,
        expires_at=result.expires_at,
        warning=result.warning,
        error=result.error,
        message=result.message,
    )
