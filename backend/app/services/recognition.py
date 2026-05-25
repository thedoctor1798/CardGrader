import base64
import json
import mimetypes
import re
import unicodedata
import urllib.error
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import (
    CARD_RECOGNITION_MIN_SCORE,
    CARD_RECOGNITION_TOP_K,
    LOCAL_AI_MODE,
    LOCAL_AI_TIMEOUT_SECONDS,
    LOCAL_AI_WORKER_BASE_URL,
    MEDIA_DIR,
    PRICE_FETCH_AFTER_RECOGNITION,
    ROOT,
)
from ..models import Card, CardMedia, OwnedCard, RecognitionAttempt, RecognitionCandidate
from ..models.core import utc_now
from ..schemas.prices import PriceFetchRequest
from .local_ai import LocalAIHTTPError, http_json, remote_worker_headers
from .price_service import fetch_prices_for_card


def safe_media_path(media: CardMedia) -> Path:
    path = (ROOT / media.file_path).resolve()
    root = ROOT.resolve()
    media_root = MEDIA_DIR.resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if path != media_root and media_root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return path


def image_payload_for_media(media: CardMedia) -> dict[str, str]:
    path = safe_media_path(media)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return {
        "label": f"{media.label or 'card'}_full",
        "mime_type": mime_type,
        "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def extracted_from_worker(worker_response: dict[str, Any]) -> dict[str, Any]:
    extracted = worker_response.get("extracted")
    if isinstance(extracted, dict):
        return extracted
    return {}


def create_attempt(session: Session, media: CardMedia) -> RecognitionAttempt:
    attempt = RecognitionAttempt(
        media_id=media.id,
        owned_card_id=media.owned_card_id,
        status="pending",
        mode=LOCAL_AI_MODE if LOCAL_AI_MODE in {"remote_worker", "server_local"} else "fallback",
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def update_attempt_from_extraction(
    session: Session,
    attempt: RecognitionAttempt,
    worker_response: dict[str, Any],
) -> RecognitionAttempt:
    extracted = extracted_from_worker(worker_response)
    attempt.status = "completed"
    attempt.extracted_name = value_or_none(extracted.get("name"))
    attempt.extracted_card_number = value_or_none(extracted.get("card_number"))
    attempt.extracted_set_text = value_or_none(extracted.get("set_text"))
    attempt.extracted_set_code = value_or_none(extracted.get("set_code"))
    attempt.extracted_rarity = value_or_none(extracted.get("rarity"))
    attempt.extracted_language = value_or_none(extracted.get("language"))
    attempt.extracted_raw_json = json.dumps(worker_response, ensure_ascii=False)
    attempt.updated_at = utc_now()
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def fail_attempt(
    session: Session,
    attempt: RecognitionAttempt,
    error_code: str,
    message: str,
    raw_json: dict[str, Any] | None = None,
) -> RecognitionAttempt:
    attempt.status = "failed"
    attempt.error_code = error_code
    attempt.error_message = message
    attempt.extracted_raw_json = json.dumps(raw_json, ensure_ascii=False) if raw_json is not None else attempt.extracted_raw_json
    attempt.updated_at = utc_now()
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def value_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def normalize_set_code(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_card_number(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^(no\.?|#)\s*", "", text)
    text = text.split("/")[0]
    match = re.search(r"[a-z]*\d+[a-z]*", text)
    return match.group(0).upper() if match else re.sub(r"[^A-Z0-9]", "", text.upper())


def fuzzy_ratio(left: Any, right: Any) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def score_catalog_card(card: Card, extracted: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    number_score = 0.0
    extracted_number = normalize_card_number(extracted.get("card_number"))
    card_number = normalize_card_number(card.card_number)
    if extracted_number and card_number:
        if extracted_number == card_number:
            number_score = 40.0
            reasons.append(f"Exact card number match: {extracted_number}")
        elif extracted_number in card_number or card_number in extracted_number:
            number_score = 32.0
            reasons.append(f"Normalized card number match: {extracted_number}")

    name_score = 0.0
    extracted_name = normalize_text(extracted.get("name"))
    card_name = normalize_text(card.name)
    if extracted_name and card_name:
        if extracted_name == card_name:
            name_score = 30.0
            reasons.append(f"Exact name match: {card.name}")
        else:
            ratio = fuzzy_ratio(extracted_name, card_name)
            if ratio >= 0.65:
                name_score = round(30.0 * ratio, 1)
                reasons.append(f"Fuzzy name match: {card.name}")

    set_score = 0.0
    extracted_code = normalize_set_code(extracted.get("set_code"))
    card_code = normalize_set_code(card.set_code)
    if extracted_code and card_code and extracted_code == card_code:
        set_score += 12.0
        reasons.append(f"Set code match: {card.set_code}")
    set_text = extracted.get("set_text")
    if set_text and card.set_name:
        ratio = fuzzy_ratio(set_text, card.set_name)
        if ratio >= 0.55:
            set_text_score = round(8.0 * ratio, 1)
            set_score += set_text_score
            reasons.append(f"Set name/text match: {card.set_name}")
    set_score = min(20.0, set_score)

    rarity_score = 0.0
    if extracted.get("rarity") and card.rarity:
        ratio = fuzzy_ratio(extracted.get("rarity"), card.rarity)
        if ratio >= 0.65:
            rarity_score = round(5.0 * ratio, 1)
            reasons.append(f"Rarity match: {card.rarity}")

    language_score = 0.0
    extracted_language = normalize_text(extracted.get("language"))
    card_language = normalize_text(card.language)
    if extracted_language and card_language and extracted_language == card_language:
        language_score = 5.0
        reasons.append(f"Language match: {card.language}")

    total = min(100.0, number_score + name_score + set_score + rarity_score + language_score)
    return {
        "score": round(total, 1),
        "match_reasons": reasons,
        "name_score": name_score,
        "number_score": number_score,
        "set_score": round(set_score, 1),
        "rarity_score": rarity_score,
        "language_score": language_score,
    }


def match_catalog(session: Session, extracted: dict[str, Any]) -> list[tuple[Card, dict[str, Any]]]:
    cards = session.exec(select(Card).order_by(Card.id)).all()
    scored = []
    for card in cards:
        score = score_catalog_card(card, extracted)
        if score["score"] >= CARD_RECOGNITION_MIN_SCORE:
            scored.append((card, score))
    scored.sort(key=lambda item: (-item[1]["score"], item[0].id or 0))
    return scored[:CARD_RECOGNITION_TOP_K]


def store_candidates(
    session: Session,
    attempt: RecognitionAttempt,
    scored_cards: list[tuple[Card, dict[str, Any]]],
) -> list[RecognitionCandidate]:
    candidates: list[RecognitionCandidate] = []
    for index, (card, score) in enumerate(scored_cards, start=1):
        candidate = RecognitionCandidate(
            recognition_attempt_id=attempt.id,
            catalog_card_id=card.id,
            score=score["score"],
            rank=index,
            match_reasons=json.dumps(score["match_reasons"], ensure_ascii=False),
            name_score=score["name_score"],
            number_score=score["number_score"],
            set_score=score["set_score"],
            rarity_score=score["rarity_score"],
            language_score=score["language_score"],
        )
        session.add(candidate)
        candidates.append(candidate)
    session.commit()
    for candidate in candidates:
        session.refresh(candidate)
    return candidates


def attempt_read(attempt: RecognitionAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "media_id": attempt.media_id,
        "owned_card_id": attempt.owned_card_id,
        "status": attempt.status,
        "mode": attempt.mode,
        "extracted": {
            "name": attempt.extracted_name,
            "card_number": attempt.extracted_card_number,
            "set_text": attempt.extracted_set_text,
            "set_code": attempt.extracted_set_code,
            "rarity": attempt.extracted_rarity,
            "language": attempt.extracted_language,
        },
        "error_code": attempt.error_code,
        "error_message": attempt.error_message,
        "created_at": attempt.created_at,
        "updated_at": attempt.updated_at,
    }


def candidate_read(session: Session, candidate: RecognitionCandidate) -> dict[str, Any]:
    card = session.get(Card, candidate.catalog_card_id)
    reasons = []
    if candidate.match_reasons:
        try:
            parsed = json.loads(candidate.match_reasons)
            if isinstance(parsed, list):
                reasons = [str(item) for item in parsed]
        except json.JSONDecodeError:
            reasons = [candidate.match_reasons]
    return {
        "id": candidate.id,
        "recognition_attempt_id": candidate.recognition_attempt_id,
        "catalog_card_id": candidate.catalog_card_id,
        "rank": candidate.rank,
        "score": candidate.score,
        "name": card.name if card else "-",
        "set_name": card.set_name if card else None,
        "set_code": card.set_code if card else None,
        "card_number": card.card_number if card else None,
        "rarity": card.rarity if card else None,
        "language": card.language if card else None,
        "match_reasons": reasons,
        "name_score": candidate.name_score,
        "number_score": candidate.number_score,
        "set_score": candidate.set_score,
        "rarity_score": candidate.rarity_score,
        "language_score": candidate.language_score,
    }


def call_remote_recognition_worker(media: CardMedia) -> dict[str, Any]:
    if LOCAL_AI_MODE != "remote_worker":
        raise HTTPException(status_code=400, detail="Card recognition currently requires LOCAL_AI_MODE=remote_worker.")
    if not LOCAL_AI_WORKER_BASE_URL.strip():
        raise HTTPException(status_code=400, detail="LOCAL_AI_WORKER_BASE_URL is not configured.")
    payload = {
        "media_id": str(media.id),
        "images": [image_payload_for_media(media)],
        "recognition_profile": "pokemon_tcg_default",
    }
    url = f"{LOCAL_AI_WORKER_BASE_URL.rstrip('/')}/api/ai/recognize-card"
    print(
        "Card recognition worker request",
        {"media_id": media.id, "url": url, "timeout": LOCAL_AI_TIMEOUT_SECONDS, "images": len(payload["images"])},
    )
    try:
        return http_json("POST", url, payload, timeout_seconds=LOCAL_AI_TIMEOUT_SECONDS, headers=remote_worker_headers())
    except LocalAIHTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": "remote_ai_worker_error",
                "message": f"Windows AI worker returned HTTP {exc.status_code}.",
                "response_preview": exc.response_body[:1000],
            },
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Card recognition worker unreachable: {exc}")
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": "remote_ai_worker_unreachable",
                "message": (
                    "CardGrader backend could not reach the Windows AI worker. "
                    "Check Tailscale, worker service, firewall, and LM Studio."
                ),
            },
        ) from exc


def recognize_media_card(session: Session, media_id: int) -> dict[str, Any]:
    media = session.get(CardMedia, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found.")
    if media.media_type != "image":
        raise HTTPException(status_code=400, detail="Only image media can be recognized.")
    safe_media_path(media)

    print(f"Card recognition requested media_id={media_id} mode={LOCAL_AI_MODE}")
    attempt = create_attempt(session, media)
    try:
        worker_response = call_remote_recognition_worker(media)
        if not worker_response.get("ok"):
            error = str(worker_response.get("error") or "card_recognition_failed")
            message = str(worker_response.get("message") or "Could not recognize card from image.")
            attempt = fail_attempt(session, attempt, error, message, worker_response)
            return {
                "ok": False,
                "error": error,
                "message": message,
                "recognition_attempt_id": attempt.id,
                "recognition_attempt": attempt_read(attempt),
                "candidates": [],
            }
        extracted = extracted_from_worker(worker_response)
        if not any(value_or_none(extracted.get(key)) for key in ["name", "card_number", "set_text", "set_code"]):
            attempt = fail_attempt(
                session,
                attempt,
                "card_text_not_readable",
                "The model could not reliably extract identifying card text from the image.",
                worker_response,
            )
            return {
                "ok": False,
                "error": "card_text_not_readable",
                "message": "The model could not reliably extract identifying card text from the image.",
                "recognition_attempt_id": attempt.id,
                "recognition_attempt": attempt_read(attempt),
                "candidates": [],
            }
        attempt = update_attempt_from_extraction(session, attempt, worker_response)
        scored = match_catalog(session, extracted)
        candidates = store_candidates(session, attempt, scored)
        print(
            "Card recognition completed",
            {"media_id": media_id, "attempt_id": attempt.id, "candidates": len(candidates), "extracted": attempt_read(attempt)["extracted"]},
        )
        return {
            "ok": True,
            "recognition_attempt": attempt_read(attempt),
            "candidates": [candidate_read(session, candidate) for candidate in candidates],
        }
    except HTTPException as exc:
        message = exc.detail if isinstance(exc.detail, str) else "Card recognition failed."
        fail_attempt(session, attempt, "card_recognition_failed", str(message))
        raise
    except Exception as exc:
        attempt = fail_attempt(session, attempt, "card_recognition_failed", "Could not recognize card from image.")
        print(f"Card recognition failed attempt_id={attempt.id}: {exc}")
        return {
            "ok": False,
            "error": "card_recognition_failed",
            "message": "Could not recognize card from image.",
            "recognition_attempt_id": attempt.id,
            "recognition_attempt": attempt_read(attempt),
            "candidates": [],
        }


def accept_recognition_candidate(
    session: Session,
    attempt_id: int,
    catalog_card_id: int,
    owned_card_id: int | None,
    create_owned_card: bool,
) -> dict[str, Any]:
    attempt = session.get(RecognitionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Recognition attempt not found.")
    card = session.get(Card, catalog_card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Catalog card not found.")
    media = session.get(CardMedia, attempt.media_id)

    if create_owned_card:
        owned_card = OwnedCard(card_id=card.id, status="raw_owned", acquired_source="unknown")
        session.add(owned_card)
        session.commit()
        session.refresh(owned_card)
    else:
        target_owned_id = owned_card_id or attempt.owned_card_id
        if target_owned_id is None:
            raise HTTPException(status_code=400, detail="owned_card_id is required when create_owned_card is false.")
        owned_card = session.get(OwnedCard, target_owned_id)
        if owned_card is None:
            raise HTTPException(status_code=404, detail="Owned card not found.")
        owned_card.card_id = card.id
        owned_card.updated_at = utc_now()
        session.add(owned_card)
        session.commit()
        session.refresh(owned_card)

    if media is not None:
        media.owned_card_id = owned_card.id
        session.add(media)
    attempt.owned_card_id = owned_card.id
    attempt.status = "accepted"
    attempt.updated_at = utc_now()
    session.add(attempt)
    session.commit()
    session.refresh(owned_card)
    if PRICE_FETCH_AFTER_RECOGNITION:
        try:
            fetch_prices_for_card(
                session,
                card.id,
                PriceFetchRequest(owned_card_id=owned_card.id),
            )
        except Exception as exc:  # noqa: BLE001 - recognition accept should not fail on optional pricing
            print(f"Price fetch after recognition failed owned_card_id={owned_card.id}: {exc}")
    print("Card recognition accepted", {"attempt_id": attempt.id, "catalog_card_id": card.id, "owned_card_id": owned_card.id})
    return {
        "ok": True,
        "owned_card": {
            "id": owned_card.id,
            "catalog_card_id": card.id,
            "card_id": card.id,
            "name": card.name,
            "set_name": card.set_name,
            "set_code": card.set_code,
            "card_number": card.card_number,
            "rarity": card.rarity,
            "language": card.language,
        },
    }
