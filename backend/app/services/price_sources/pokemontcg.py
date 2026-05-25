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
    get_json,
    map_cardmarket_prices,
    map_tcgplayer_prices,
    merge_price_data,
)


class PokemonTCGPriceSource(PriceSource):
    source_name = "pokemontcg"

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
            return self._error(card, "price_source_disabled", "Pokemon TCG API provider is disabled.")

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        mapping = get_provider_mapping(session, self.source_name, card.id or 0) if card.id is not None else None
        if mapping is not None:
            return self._fetch_mapped_card(card, mapping.source_card_id, mapping.match_score, mapping.source_url, headers)

        query_parts = [f'name:"{card.name}"']
        if card.set_code:
            query_parts.append(f"set.ptcgoCode:{card.set_code}")
        if card.card_number:
            query_parts.append(f"number:{card.card_number.split('/')[0]}")
        search_url = build_url(
            str(self.config["base_url"]),
            "/cards",
            {
                "q": " ".join(query_parts),
                "page": 1,
                "pageSize": 20,
            },
        )
        debug_metadata = {
            "provider": self.source_name,
            "search_url": search_url,
            "authenticated": bool(self.api_key),
            "matched_search_terms": {
                "name": card.name,
                "set_name": card.set_name,
                "set_code": card.set_code,
                "card_number": card.card_number,
                "rarity": card.rarity,
            },
        }

        try:
            search_response = get_json(search_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
        except ProviderHttpError as exc:
            if exc.status_code in {401, 403}:
                return PriceSourceResult(
                    ok=False,
                    source=self.source_name,
                    card_id=card.id or 0,
                    raw_response=exc.response.data if exc.response else None,
                    debug_metadata=debug_metadata,
                    error="provider_auth_failed",
                    message="Pokemon TCG API key was rejected.",
                )
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                raw_response=exc.response.data if exc.response else None,
                debug_metadata=debug_metadata,
                error="provider_error",
                message=str(exc),
            )

        candidates = extract_items(search_response.data)
        candidate, score, reasons, alternatives = best_candidate(card, candidates)
        debug_metadata["candidate_alternatives"] = alternatives
        debug_metadata["match_score"] = score
        debug_metadata["match_reasons"] = reasons
        if candidate is None or score < float(self.config.get("min_match_score") or 70):
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                raw_response=search_response.data,
                debug_metadata=debug_metadata,
                match_score=score,
                error="provider_no_reliable_match",
                message="Pokemon TCG API did not return a reliable enough card match.",
            )

        source_card_id = str(candidate.get("id") or "")
        detail = candidate
        detail_url = build_url(str(self.config["base_url"]), f"/cards/{source_card_id}") if source_card_id else search_url
        if source_card_id and not candidate.get("tcgplayer") and not candidate.get("cardmarket"):
            try:
                detail_response = get_json(detail_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
                detail = card_detail(detail_response.data) or candidate
            except ProviderHttpError:
                detail = candidate

        prices = map_pokemontcg_price_data(detail)
        if prices is None or not prices.has_any_price():
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=source_card_id or None,
                source_url=detail.get("tcgplayer", {}).get("url") if isinstance(detail.get("tcgplayer"), dict) else detail_url,
                raw_response=detail,
                debug_metadata=debug_metadata,
                match_score=score,
                error="provider_no_price_available",
                message="Pokemon TCG API did not return raw marketplace prices for this card.",
            )

        return PriceSourceResult(
            ok=True,
            source=self.source_name,
            card_id=card.id or 0,
            source_card_id=source_card_id or None,
            source_url=detail.get("tcgplayer", {}).get("url") if isinstance(detail.get("tcgplayer"), dict) else detail_url,
            prices=prices,
            confidence="high" if score >= 90 else "medium",
            condition_hint="raw marketplace",
            raw_response=detail,
            debug_metadata=debug_metadata,
            match_score=score,
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
            "authenticated": bool(self.api_key),
        }
        try:
            detail_response = get_json(detail_url, headers=headers, timeout=int(self.config["timeout_seconds"]))
        except ProviderHttpError as exc:
            if exc.status_code in {401, 403}:
                return PriceSourceResult(
                    ok=False,
                    source=self.source_name,
                    card_id=card.id or 0,
                    source_card_id=source_card_id,
                    source_url=mapped_source_url or detail_url,
                    raw_response=exc.response.data if exc.response else None,
                    debug_metadata=debug_metadata,
                    match_score=match_score,
                    error="provider_auth_failed",
                    message="Pokemon TCG API key was rejected.",
                )
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=source_card_id,
                source_url=mapped_source_url or detail_url,
                raw_response=exc.response.data if exc.response else None,
                debug_metadata=debug_metadata,
                match_score=match_score,
                error="provider_error",
                message=str(exc),
            )

        detail = card_detail(detail_response.data) or {}
        prices = map_pokemontcg_price_data(detail)
        source_url = detail.get("tcgplayer", {}).get("url") if isinstance(detail.get("tcgplayer"), dict) else detail_url
        if prices is None or not prices.has_any_price():
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=source_card_id,
                source_url=mapped_source_url or source_url,
                raw_response=detail,
                debug_metadata=debug_metadata,
                match_score=match_score,
                error="provider_no_price_available",
                message="Mapped Pokemon TCG API card did not return raw marketplace prices.",
            )

        score = match_score if match_score is not None else 100.0
        return PriceSourceResult(
            ok=True,
            source=self.source_name,
            card_id=card.id or 0,
            source_card_id=source_card_id,
            source_url=mapped_source_url or source_url,
            prices=prices,
            confidence="manual" if match_score is None else ("high" if score >= 90 else "medium"),
            condition_hint="raw marketplace",
            raw_response=detail,
            debug_metadata=debug_metadata,
            match_score=score,
        )

    def _error(self, card: Card, error: str, message: str) -> PriceSourceResult:
        return PriceSourceResult(
            ok=False,
            source=self.source_name,
            card_id=card.id or 0,
            error=error,
            message=message,
            debug_metadata={"provider": self.source_name},
        )


def map_pokemontcg_price_data(payload: dict[str, Any]) -> PriceData | None:
    tcgplayer = map_tcgplayer_prices(payload.get("tcgplayer") if isinstance(payload.get("tcgplayer"), dict) else None)
    cardmarket = map_cardmarket_prices(payload.get("cardmarket") if isinstance(payload.get("cardmarket"), dict) else None)
    return merge_price_data(tcgplayer, cardmarket)
