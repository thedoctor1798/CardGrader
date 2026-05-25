from typing import Any

from sqlmodel import Session

from ...config import PRICE_EXTERNAL_FETCH_ENABLED
from ...models import Card
from ..price_provider_mappings import get_provider_mapping
from ..provider_settings import EffectiveProviderConfig
from .base import PriceData, PriceSource, PriceSourceResult
from .common import (
    ProviderHttpError,
    best_candidate,
    build_url,
    card_detail,
    extract_items,
    first_float,
    get_json,
    int_header,
    low_remaining_warning,
    optional_float,
    rate_limit_headers,
)


RAW_TIERS = ("NEAR_MINT", "NM", "MINT", "AGGREGATED", "RAW", "LIGHTLY_PLAYED", "EXCELLENT")
PSA_TIERS = ("PSA_7", "PSA_8", "PSA_9", "PSA_10")


class PokeTracePriceSource(PriceSource):
    source_name = "poketrace"

    def __init__(self, effective_config: EffectiveProviderConfig):
        self.effective = effective_config
        self.config = effective_config.config
        self.api_key = str(effective_config.secrets.get("api_key") or "")

    def fetch(
        self,
        session: Session,
        card: Card,
        owned_card_id: int | None = None,
    ) -> PriceSourceResult:
        del owned_card_id
        if not PRICE_EXTERNAL_FETCH_ENABLED:
            return self._error(card, "price_source_disabled", "External price fetching is disabled.")
        if not self.effective.enabled:
            return self._error(card, "price_source_disabled", "PokeTrace provider is disabled.")
        if not self.api_key:
            return self._error(card, "price_source_not_configured", "PokeTrace API key is not configured.")

        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        mapping = get_provider_mapping(session, self.source_name, card.id or 0) if card.id is not None else None
        if mapping is not None:
            return self._fetch_mapped_card(card, mapping.source_card_id, mapping.match_score, mapping.source_url, headers)

        search_terms = self._search_terms(card)
        search_url = build_url(
            str(self.config["base_url"]),
            "/cards",
            {
                "search": search_terms,
                "market": self.config.get("market", "US"),
                "product_type": "single",
                "limit": 20,
            },
        )
        debug_metadata: dict[str, Any] = {
            "provider": self.source_name,
            "matched_search_terms": {
                "name": card.name,
                "set_name": card.set_name,
                "set_code": card.set_code,
                "card_number": card.card_number,
                "rarity": card.rarity,
                "market": self.config.get("market"),
            },
            "search_url": search_url,
            "plan": self.config.get("plan"),
        }

        try:
            search_response = get_json(search_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
        except ProviderHttpError as exc:
            return self._http_error(card, exc, debug_metadata)

        rate_limit = rate_limit_headers(search_response.headers)
        if rate_limit:
            debug_metadata["rate_limit"] = rate_limit
        if search_response.status_code == 429:
            return self._rate_limited(card, search_response.data, rate_limit, debug_metadata)

        candidates = extract_items(search_response.data)
        candidate, score, reasons, alternatives = best_candidate(card, candidates)
        debug_metadata["candidate_alternatives"] = alternatives
        debug_metadata["match_score"] = score
        debug_metadata["match_reasons"] = reasons
        min_score = float(self.config.get("min_match_score") or 70)
        if candidate is None or score < min_score:
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                raw_response=search_response.data,
                debug_metadata=debug_metadata,
                match_score=score,
                rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
                error="provider_no_reliable_match",
                message="PokeTrace did not return a reliable enough card match.",
            )

        source_card_id = str(candidate.get("id") or "")
        detail = candidate
        detail_url = build_url(str(self.config["base_url"]), f"/cards/{source_card_id}") if source_card_id else search_url
        if source_card_id and not isinstance(candidate.get("prices"), dict):
            try:
                detail_response = get_json(detail_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
                detail_rate_limit = rate_limit_headers(detail_response.headers)
                if detail_rate_limit:
                    debug_metadata["rate_limit"] = {**rate_limit, **detail_rate_limit}
                    rate_limit = debug_metadata["rate_limit"]
                if detail_response.status_code == 429:
                    return self._rate_limited(card, detail_response.data, rate_limit, debug_metadata)
                detail = card_detail(detail_response.data) or candidate
            except ProviderHttpError as exc:
                return self._http_error(card, exc, debug_metadata)

        prices, condition_hint, mapping_warning = map_poketrace_price_data(detail, str(self.config.get("market") or "US"))
        warning = mapping_warning or low_remaining_warning(rate_limit)
        if prices is None or not prices.has_any_price():
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=source_card_id or None,
                source_url=detail_url,
                raw_response=detail,
                debug_metadata=debug_metadata,
                match_score=score,
                rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
                warning=warning,
                error="provider_no_price_available",
                message="PokeTrace did not return usable price data for this card.",
            )

        return PriceSourceResult(
            ok=True,
            source=self.source_name,
            card_id=card.id or 0,
            source_card_id=source_card_id or None,
            source_url=detail_url,
            prices=prices,
            confidence="high" if score >= 90 else "medium",
            condition_hint=condition_hint,
            raw_response=detail,
            debug_metadata=debug_metadata,
            match_score=score,
            rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
            warning=warning,
        )

    def _fetch_mapped_card(
        self,
        card: Card,
        source_card_id: str,
        match_score: float | None,
        mapped_source_url: str | None,
        headers: dict[str, str],
    ) -> PriceSourceResult:
        detail_url = build_url(str(self.config["base_url"]), f"/cards/{source_card_id}")
        debug_metadata: dict[str, Any] = {
            "provider": self.source_name,
            "mapping_source": "manual_provider_mapping",
            "source_card_id": source_card_id,
            "source_url": mapped_source_url or detail_url,
            "match_score": match_score,
        }
        try:
            detail_response = get_json(detail_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
        except ProviderHttpError as exc:
            return self._http_error(card, exc, debug_metadata)

        rate_limit = rate_limit_headers(detail_response.headers)
        if rate_limit:
            debug_metadata["rate_limit"] = rate_limit
        if detail_response.status_code == 429:
            return self._rate_limited(card, detail_response.data, rate_limit, debug_metadata)

        detail = card_detail(detail_response.data) or {}
        prices, condition_hint, mapping_warning = map_poketrace_price_data(detail, str(self.config.get("market") or "US"))
        warning = mapping_warning or low_remaining_warning(rate_limit)
        if prices is None or not prices.has_any_price():
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=source_card_id,
                source_url=mapped_source_url or detail_url,
                raw_response=detail,
                debug_metadata=debug_metadata,
                match_score=match_score,
                rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
                warning=warning,
                error="provider_no_price_available",
                message="Mapped PokeTrace card did not return usable price data.",
            )

        score = match_score if match_score is not None else 100.0
        return PriceSourceResult(
            ok=True,
            source=self.source_name,
            card_id=card.id or 0,
            source_card_id=source_card_id,
            source_url=mapped_source_url or detail_url,
            prices=prices,
            confidence="manual" if match_score is None else ("high" if score >= 90 else "medium"),
            condition_hint=condition_hint,
            raw_response=detail,
            debug_metadata=debug_metadata,
            match_score=score,
            rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
            warning=warning,
        )

    def _search_terms(self, card: Card) -> str:
        return " ".join(
            part
            for part in (card.name, card.set_name, card.set_code, card.card_number, card.rarity)
            if part
        )

    def _error(self, card: Card, error: str, message: str) -> PriceSourceResult:
        return PriceSourceResult(
            ok=False,
            source=self.source_name,
            card_id=card.id or 0,
            error=error,
            message=message,
            debug_metadata={"provider": self.source_name, "plan": self.config.get("plan")},
        )

    def _http_error(self, card: Card, exc: ProviderHttpError, debug_metadata: dict[str, Any]) -> PriceSourceResult:
        response = exc.response
        if response is not None:
            rate_limit = rate_limit_headers(response.headers)
            if rate_limit:
                debug_metadata["rate_limit"] = rate_limit
            if exc.status_code in {401, 403}:
                return PriceSourceResult(
                    ok=False,
                    source=self.source_name,
                    card_id=card.id or 0,
                    raw_response=response.data,
                    debug_metadata=debug_metadata,
                    error="provider_auth_failed",
                    message="PokeTrace API key was rejected.",
                )
        return PriceSourceResult(
            ok=False,
            source=self.source_name,
            card_id=card.id or 0,
            raw_response=response.data if response else None,
            debug_metadata=debug_metadata,
            error="provider_error",
            message=str(exc),
        )

    def _rate_limited(
        self,
        card: Card,
        raw_response: Any,
        rate_limit: dict[str, Any],
        debug_metadata: dict[str, Any],
    ) -> PriceSourceResult:
        retry_after = int_header(rate_limit, "Retry-After")
        return PriceSourceResult(
            ok=False,
            source=self.source_name,
            card_id=card.id or 0,
            raw_response=raw_response,
            debug_metadata={**debug_metadata, "rate_limit": rate_limit, "retry_after": retry_after},
            rate_limit_remaining=int_header(rate_limit, "X-RateLimit-Remaining"),
            warning="provider_rate_limited",
            error="provider_rate_limited",
            message="PokeTrace rate limit reached. Try again later.",
        )


def map_poketrace_price_data(payload: dict[str, Any], market: str) -> tuple[PriceData | None, str | None, str | None]:
    prices = payload.get("prices") if isinstance(payload.get("prices"), dict) else {}
    currency = str(payload.get("currency") or ("EUR" if market.upper() == "EU" else "USD")).upper()
    preferred_sources = (
        ("cardmarket", "cardmarket_unsold", "ebay", "tcgplayer")
        if market.upper() == "EU"
        else ("tcgplayer", "ebay", "cardmarket", "cardmarket_unsold")
    )

    raw_entry: dict[str, Any] | None = None
    raw_source = None
    raw_tier = None
    for source in preferred_sources:
        section = prices.get(source)
        if not isinstance(section, dict):
            continue
        raw_tier, raw_entry = first_tier(section, RAW_TIERS)
        if raw_entry:
            raw_source = source
            break

    raw_market = first_float(raw_entry or {}, ("avg", "market", "marketPrice", "average", "trend"))
    raw_low = first_float(raw_entry or {}, ("low", "min"))
    raw_high = first_float(raw_entry or {}, ("high", "max"))

    graded_values: dict[str, float | None] = {}
    for tier in PSA_TIERS:
        graded_values[tier.lower()] = None
        for source in preferred_sources:
            section = prices.get(source)
            if not isinstance(section, dict):
                continue
            _, entry = first_tier(section, (tier,))
            value = first_float(entry or {}, ("avg", "market", "marketPrice", "average"))
            if value is not None:
                graded_values[tier.lower()] = value
                break

    result = PriceData(
        raw_price=raw_market,
        market_price=raw_market,
        low_price=raw_low,
        high_price=raw_high,
        psa_7=graded_values["psa_7"],
        psa_8=graded_values["psa_8"],
        psa_9=graded_values["psa_9"],
        psa_10=graded_values["psa_10"],
        currency=currency,
    )
    warning = None
    if not any(graded_values.values()) and str(payload.get("market") or market).upper() == "US":
        warning = "provider_plan_limited"
    condition_hint = f"{raw_source or 'unknown'} {raw_tier or 'raw'}".strip()
    return (result if result.has_any_price() else None), condition_hint, warning


def first_tier(section: dict[str, Any], tier_names: tuple[str, ...]) -> tuple[str | None, dict[str, Any] | None]:
    normalized = {str(key).upper().replace(" ", "_").replace("-", "_"): key for key in section}
    for tier_name in tier_names:
        key = normalized.get(tier_name.upper().replace("-", "_"))
        value = section.get(key) if key is not None else None
        if isinstance(value, dict):
            return tier_name, value
    for key, value in section.items():
        normalized_key = str(key).upper().replace(" ", "_").replace("-", "_")
        if any(tier in normalized_key for tier in tier_names) and isinstance(value, dict):
            return str(key), value
    return None, None
