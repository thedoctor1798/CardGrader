import json
from pathlib import Path
from typing import Any

from sqlmodel import Session

from ...config import CATALOG_DIR, DATA_DIR, PRICE_DEFAULT_CURRENCY
from ...models import Card
from .base import PriceData, PriceSource, PriceSourceResult


PRICE_FIELD_ALIASES = {
    "raw_price": ("raw_price", "raw", "raw_price_huf"),
    "market_price": ("market_price", "market", "market_price_huf"),
    "low_price": ("low_price", "low", "low_price_huf"),
    "high_price": ("high_price", "high", "high_price_huf"),
    "psa_7": ("psa_7", "psa7", "psa_7_price_huf"),
    "psa_8": ("psa_8", "psa8", "psa_8_price_huf"),
    "psa_9": ("psa_9", "psa9", "psa_9_price_huf"),
    "psa_10": ("psa_10", "psa10", "psa_10_price_huf"),
}


class LocalJsonPriceSource(PriceSource):
    source_name = "local_json"

    def fetch(
        self,
        session: Session,
        card: Card,
        owned_card_id: int | None = None,
    ) -> PriceSourceResult:
        del session, owned_card_id
        checked_paths = []
        for path in self._candidate_paths(card):
            checked_paths.append(str(path))
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return PriceSourceResult(
                    ok=False,
                    source=self.source_name,
                    card_id=card.id or 0,
                    error="invalid_provider_response",
                    message=f"Local JSON price file could not be read: {path.name}",
                    debug_metadata={"provider": self.source_name, "path": str(path), "error": str(exc)},
                )

            entry = self._find_card_entry(payload, card)
            if entry is None:
                continue

            prices = self._prices_from_entry(entry)
            if not prices.has_any_price():
                return PriceSourceResult(
                    ok=False,
                    source=self.source_name,
                    card_id=card.id or 0,
                    error="invalid_provider_response",
                    message="Local JSON price entry did not contain usable price fields.",
                    raw_response=entry,
                    debug_metadata={"provider": self.source_name, "path": str(path)},
                )

            return PriceSourceResult(
                ok=True,
                source=self.source_name,
                card_id=card.id or 0,
                source_card_id=str(entry.get("source_card_id") or entry.get("id") or card.id),
                source_url=entry.get("source_url"),
                prices=prices,
                confidence=str(entry.get("confidence") or "medium"),
                condition_hint=entry.get("condition_hint"),
                raw_response=entry,
                debug_metadata={
                    "provider": self.source_name,
                    "path": str(path),
                    "matched_search_terms": self._search_terms(card),
                },
            )

        return PriceSourceResult(
            ok=False,
            source=self.source_name,
            card_id=card.id or 0,
            error="price_source_not_configured",
            message="No local JSON price file is available for this card.",
            debug_metadata={"provider": self.source_name, "checked_paths": checked_paths},
        )

    def _candidate_paths(self, card: Card) -> list[Path]:
        card_id = str(card.id)
        return [
            DATA_DIR / "prices" / f"{card_id}.json",
            CATALOG_DIR / "prices" / f"{card_id}.json",
            DATA_DIR / "prices" / "prices.json",
            CATALOG_DIR / "prices.json",
        ]

    def _find_card_entry(self, payload: Any, card: Card) -> dict[str, Any] | None:
        if isinstance(payload, dict) and self._looks_like_price_entry(payload):
            return payload

        if isinstance(payload, dict):
            cards = payload.get("cards", payload)
            if isinstance(cards, dict):
                entry = cards.get(str(card.id))
                if isinstance(entry, dict):
                    return entry
            if isinstance(cards, list):
                return self._find_in_list(cards, card)

        if isinstance(payload, list):
            return self._find_in_list(payload, card)

        return None

    def _find_in_list(self, items: list[Any], card: Card) -> dict[str, Any] | None:
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("card_id") == card.id or str(item.get("card_id")) == str(card.id):
                return item
            if self._card_identity_matches(item, card):
                return item
        return None

    def _card_identity_matches(self, item: dict[str, Any], card: Card) -> bool:
        name = str(item.get("name") or "").strip().lower()
        set_code = str(item.get("set_code") or "").strip().lower()
        number = str(item.get("card_number") or "").strip().lower()
        return (
            bool(name)
            and name == (card.name or "").strip().lower()
            and set_code == (card.set_code or "").strip().lower()
            and number == (card.card_number or "").strip().lower()
        )

    def _prices_from_entry(self, entry: dict[str, Any]) -> PriceData:
        prices = entry.get("prices") if isinstance(entry.get("prices"), dict) else entry
        values: dict[str, float | None] = {}
        for field_name, aliases in PRICE_FIELD_ALIASES.items():
            values[field_name] = self._optional_float(first_present(prices, aliases))
        return PriceData(
            **values,
            currency=str(prices.get("currency") or entry.get("currency") or PRICE_DEFAULT_CURRENCY).upper(),
        )

    def _looks_like_price_entry(self, payload: dict[str, Any]) -> bool:
        if isinstance(payload.get("prices"), dict):
            return True
        return any(alias in payload for aliases in PRICE_FIELD_ALIASES.values() for alias in aliases)

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _search_terms(self, card: Card) -> dict[str, str | None]:
        return {
            "name": card.name,
            "set_code": card.set_code,
            "card_number": card.card_number,
        }


def first_present(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in values:
            return values[key]
    return None
