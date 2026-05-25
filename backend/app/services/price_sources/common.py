import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ...models import Card
from .base import PriceData


RATE_LIMIT_HEADER_NAMES = (
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "X-RateLimit-Burst-Limit",
    "X-RateLimit-Burst-Remaining",
    "Retry-After",
    "X-Plan",
)


@dataclass
class HttpJsonResponse:
    status_code: int
    data: Any
    headers: dict[str, str]
    url: str


class ProviderHttpError(RuntimeError):
    def __init__(self, status_code: int, message: str, response: HttpJsonResponse | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> HttpJsonResponse:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return HttpJsonResponse(
                status_code=response.status,
                data=json.loads(body) if body else {},
                headers={key: value for key, value in response.headers.items()},
                url=url,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"error": body}
        response = HttpJsonResponse(
            status_code=exc.code,
            data=data,
            headers={key: value for key, value in exc.headers.items()},
            url=url,
        )
        if exc.code == 429:
            return response
        raise ProviderHttpError(exc.code, str(data.get("message") or data.get("error") or exc.reason), response)
    except urllib.error.URLError as exc:
        raise TimeoutError(str(exc.reason)) from exc


def build_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    base = base_url.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
    return f"{base}{clean_path}" + (f"?{query}" if query else "")


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "cards", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_items(value)
            if nested:
                return nested
    return [payload] if looks_like_card(payload) else []


def card_detail(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else None


def looks_like_card(payload: dict[str, Any]) -> bool:
    return bool(payload.get("name") and (payload.get("id") or payload.get("cardNumber") or payload.get("number") or payload.get("localId")))


def score_provider_candidate(card: Card, candidate: dict[str, Any]) -> tuple[float, list[str]]:
    name = str(candidate.get("name") or "")
    number = str(candidate.get("cardNumber") or candidate.get("number") or candidate.get("localId") or "")
    rarity = str(candidate.get("rarity") or "")
    language = str(candidate.get("language") or candidate.get("lang") or "")
    set_payload = candidate.get("set") if isinstance(candidate.get("set"), dict) else {}
    set_name = str(candidate.get("setName") or candidate.get("set_name") or set_payload.get("name") or "")
    set_code = str(candidate.get("setCode") or candidate.get("set_code") or set_payload.get("id") or set_payload.get("slug") or "")

    score = 0.0
    reasons: list[str] = []

    local_name = normalize_text(card.name)
    remote_name = normalize_text(name)
    if local_name and remote_name:
        if local_name == remote_name:
            score += 35
            reasons.append("exact name")
        else:
            ratio = SequenceMatcher(None, local_name, remote_name).ratio()
            if ratio >= 0.72:
                score += min(33, ratio * 35)
                reasons.append(f"name similarity {round(ratio, 2)}")

    local_number = normalize_card_number(card.card_number)
    remote_number = normalize_card_number(number)
    if local_number and remote_number:
        if local_number == remote_number:
            score += 30
            reasons.append("exact card number")
        elif local_number.split("/")[0] == remote_number.split("/")[0]:
            score += 22
            reasons.append("local card number")

    local_set_code = normalize_text(card.set_code)
    remote_set_code = normalize_text(set_code)
    local_set_name = normalize_text(card.set_name)
    remote_set_name = normalize_text(set_name)
    if local_set_code and remote_set_code and local_set_code == remote_set_code:
        score += 20
        reasons.append("set code")
    elif local_set_name and remote_set_name:
        ratio = SequenceMatcher(None, local_set_name, remote_set_name).ratio()
        if ratio >= 0.7:
            score += min(20, ratio * 20)
            reasons.append(f"set similarity {round(ratio, 2)}")

    if normalize_text(card.rarity) and normalize_text(card.rarity) == normalize_text(rarity):
        score += 8
        reasons.append("rarity")
    if normalize_text(card.language) and normalize_text(card.language) == normalize_text(language):
        score += 7
        reasons.append("language")

    return min(100.0, round(score, 2)), reasons


def best_candidate(card: Card, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float, list[str], list[dict[str, Any]]]:
    scored = []
    for candidate in candidates:
        score, reasons = score_provider_candidate(card, candidate)
        scored.append({"candidate": candidate, "score": score, "match_reasons": reasons})
    scored.sort(key=lambda item: item["score"], reverse=True)
    if not scored:
        return None, 0.0, [], []
    best = scored[0]
    alternatives = [
        {
            "id": item["candidate"].get("id"),
            "name": item["candidate"].get("name"),
            "number": item["candidate"].get("cardNumber") or item["candidate"].get("number") or item["candidate"].get("localId"),
            "score": item["score"],
            "match_reasons": item["match_reasons"],
        }
        for item in scored[:5]
    ]
    return best["candidate"], float(best["score"]), list(best["match_reasons"]), alternatives


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_card_number(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("#", "")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_float(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in payload:
            value = optional_float(payload.get(key))
            if value is not None:
                return value
    return None


def map_tcgplayer_prices(payload: dict[str, Any] | None) -> PriceData | None:
    if not isinstance(payload, dict):
        return None
    prices = payload.get("prices") if isinstance(payload.get("prices"), dict) else payload
    variants = (
        "holofoil",
        "normal",
        "reverseHolofoil",
        "reverse-holofoil",
        "reverse",
        "unlimited-holofoil",
        "unlimited",
        "1st-edition-holofoil",
        "1st-edition",
    )
    for variant in variants:
        entry = prices.get(variant)
        if not isinstance(entry, dict):
            continue
        market = first_float(entry, ("market", "marketPrice", "mid", "midPrice"))
        low = first_float(entry, ("low", "lowPrice", "directLow", "directLowPrice"))
        high = first_float(entry, ("high", "highPrice"))
        if any(value is not None for value in (market, low, high)):
            return PriceData(
                raw_price=market,
                market_price=market,
                low_price=low,
                high_price=high,
                currency=str(payload.get("unit") or "USD").upper(),
            )
    return None


def map_cardmarket_prices(payload: dict[str, Any] | None) -> PriceData | None:
    if not isinstance(payload, dict):
        return None
    prices = payload.get("prices") if isinstance(payload.get("prices"), dict) else payload
    market = first_float(prices, ("trend", "trendPrice", "avg", "averageSellPrice", "avg30", "avg7", "avg1"))
    low = first_float(prices, ("low", "lowPrice", "low-holo"))
    high = first_float(prices, ("high", "highPrice"))
    if market is None and low is None and high is None:
        return None
    return PriceData(
        raw_price=market,
        market_price=market,
        low_price=low,
        high_price=high,
        currency=str(payload.get("unit") or "EUR").upper(),
    )


def merge_price_data(primary: PriceData | None, fallback: PriceData | None) -> PriceData | None:
    return primary if primary and primary.has_any_price() else fallback


def rate_limit_headers(headers: dict[str, str]) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    lower_headers = {key.lower(): value for key, value in headers.items()}
    for header in RATE_LIMIT_HEADER_NAMES:
        value = lower_headers.get(header.lower())
        if value is not None:
            captured[header] = value
    return captured


def int_header(headers: dict[str, Any], name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def low_remaining_warning(headers: dict[str, Any]) -> str | None:
    remaining = int_header(headers, "X-RateLimit-Remaining")
    if remaining is not None and remaining <= 10:
        return "provider_rate_limit_low"
    return None
