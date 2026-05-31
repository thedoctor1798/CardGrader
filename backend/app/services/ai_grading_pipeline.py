import base64
import hashlib
from io import BytesIO
import json
import logging
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlmodel import Session, select
from sqlalchemy import or_

from ..config import (
    AI_MAX_CONTEXT_TOKENS,
    AI_PHASE_A_MAX_OUTPUT_TOKENS,
    AI_PHASE_B_MAX_OUTPUT_TOKENS,
    AI_WORKER_SHARED_TOKEN,
    ENABLE_IMAGE_PREPROCESSING,
    ENABLE_TWO_PHASE_AI_GRADING,
    LOCAL_AI_BASE_URL,
    LOCAL_AI_CONNECT_TIMEOUT_SECONDS,
    LOCAL_AI_DISABLE_THINKING,
    LOCAL_AI_MAX_TOKENS,
    LOCAL_AI_MODE,
    LOCAL_AI_MODEL_NAME,
    LOCAL_AI_PROVIDER,
    LOCAL_AI_READ_TIMEOUT_SECONDS,
    LOCAL_AI_STREAMING_ENABLED,
    LOCAL_AI_TIMEOUT_SECONDS,
    LOCAL_AI_WORKER_BASE_URL,
    SEND_DIAGNOSTIC_IMAGES_TO_AI,
)
from ..models import AIGradingPipelineRun, AnalysisAsset, AnalysisRun, Card, CardMedia, OwnedCard
from .image_preprocessing import preprocess_owned_card, processed_payload
from .grading_parser import normalize_final_grading_result, parse_grade_range, parse_grade_value
from .ai_settings import get_ai_settings
from .local_ai import (
    LOCAL_AI_RESPONSE_FORMAT,
    LOCAL_AI_TEMPERATURE,
    LocalAIHTTPError,
    content_from_chat_response,
    extract_first_json_object,
    http_json,
    image_payload_metadata,
    local_path,
    models_from_response,
    remote_worker_headers,
    require_local_ai_enabled,
    save_text_asset,
    select_preferred_vision_model,
)

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "phase16_two_phase_v1"
PHASE_A_PROMPT_VERSION = "phase16_phase_a_v1"
PHASE_B_PROMPT_VERSION = "phase16_phase_b_v1"
PHASE_A_MAX_LONG_SIDE = 1400
PHASE_B_MAX_LONG_SIDE = 1200
AI_JPEG_QUALITY = 85


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def payload_size_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload).encode("utf-8"))


def phase_max_long_side(phase: str) -> int:
    return PHASE_A_MAX_LONG_SIDE if "Phase A" in phase else PHASE_B_MAX_LONG_SIDE


def encode_asset_for_ai(asset: AnalysisAsset, max_long_side: int) -> dict[str, Any]:
    path = local_path(asset.file_path)
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_long_side, max_long_side), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=AI_JPEG_QUALITY, optimize=True)
            image_bytes = buffer.getvalue()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Could not prepare AI image payload for {asset.label or asset.file_path}: {exc}") from exc
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    return {
        "label": asset.label or path.name,
        "mime_type": "image/jpeg",
        "base64": base64.b64encode(image_bytes).decode("ascii"),
        "asset_id": asset.id,
        "relative_path": str(asset.file_path),
        "filename": path.name,
        "width": width,
        "height": height,
        "file_size": len(image_bytes),
        "sha256": sha256,
        "image_hash_short": sha256[:12],
    }


def image_url_for_ai(asset: AnalysisAsset, max_long_side: int) -> dict[str, Any]:
    payload = encode_asset_for_ai(asset, max_long_side)
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{payload['mime_type']};base64,{payload['base64']}"},
    }


def requested_model_from_settings(settings: dict[str, Any] | None = None) -> str:
    model_name = str((settings or {}).get("ai_model") or LOCAL_AI_MODEL_NAME or "").strip()
    return "" if model_name.lower() == "auto" else model_name


def resolve_server_local_model(settings: dict[str, Any] | None = None) -> str:
    requested_model = requested_model_from_settings(settings)
    if requested_model:
        return requested_model
    if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
        return LOCAL_AI_MODEL_NAME
    response = http_json("GET", f"{LOCAL_AI_BASE_URL.rstrip('/')}/models", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS)
    model_name = select_preferred_vision_model(models_from_response(response))
    if not model_name:
        raise HTTPException(status_code=400, detail="No local vision model is loaded or configured.")
    return model_name


def remote_worker_status() -> dict[str, Any]:
    if not LOCAL_AI_WORKER_BASE_URL.strip():
        raise HTTPException(status_code=400, detail="LOCAL_AI_WORKER_BASE_URL is not configured.")
    base = LOCAL_AI_WORKER_BASE_URL.rstrip("/")
    last_error: Exception | None = None
    for path in ("/health", "/api/health", "/api/local-ai/status"):
        try:
            return http_json("GET", f"{base}{path}", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS, headers=remote_worker_headers())
        except Exception as exc:
            last_error = exc
            continue
    raise HTTPException(status_code=502, detail=f"Remote Local AI worker is not reachable: {last_error}")


def resolve_remote_worker_model(settings: dict[str, Any] | None = None) -> str:
    requested_model = requested_model_from_settings(settings)
    if requested_model:
        return requested_model
    if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
        return LOCAL_AI_MODEL_NAME
    status = remote_worker_status()
    model_name = str(status.get("model_name") or status.get("model") or "").strip()
    if model_name:
        return model_name
    models = [str(item) for item in status.get("models", [])] if isinstance(status.get("models"), list) else []
    model_name = select_preferred_vision_model(models)
    if not model_name:
        raise HTTPException(status_code=400, detail="No remote worker vision model is loaded or configured.")
    return model_name


def latest_pipeline_run(session: Session, owned_card_id: int) -> AIGradingPipelineRun | None:
    return session.exec(
        select(AIGradingPipelineRun)
        .where(AIGradingPipelineRun.owned_card_id == owned_card_id)
        .order_by(AIGradingPipelineRun.created_at.desc(), AIGradingPipelineRun.id.desc())
    ).first()


def latest_side_media(session: Session, owned_card_id: int, side: str) -> CardMedia | None:
    return session.exec(
        select(CardMedia)
        .where(CardMedia.owned_card_id == owned_card_id)
        .where(CardMedia.media_type == "image")
        .where(or_(CardMedia.label == side, CardMedia.label.like(f"{side}_%")))
        .order_by(CardMedia.created_at.desc(), CardMedia.id.desc())
    ).first()


def create_asset(
    session: Session,
    analysis_run_id: int,
    label: str,
    file_path: str,
    asset_type: str,
) -> AnalysisAsset:
    asset = AnalysisAsset(
        analysis_run_id=analysis_run_id,
        asset_type=asset_type,
        label=label,
        file_path=file_path,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def create_assets_for_pipeline(
    session: Session,
    analysis_run_id: int,
    owned_card_id: int,
    preprocessing: dict[str, Any],
) -> dict[str, AnalysisAsset]:
    assets: dict[str, AnalysisAsset] = {}
    for side in ("front", "back"):
        media = latest_side_media(session, owned_card_id, side)
        if media is not None:
            assets[f"{side}_original"] = create_asset(
                session,
                analysis_run_id,
                f"{side}_original",
                media.file_path,
                "phase16_original_image",
            )
        side_payload = preprocessing.get("sides", {}).get(side, {})
        generated = side_payload.get("generated_images", {})
        for key, file_path in generated.items():
            if not file_path:
                continue
            assets[f"{side}_{key}"] = create_asset(
                session,
                analysis_run_id,
                f"{side}_{key}",
                file_path,
                "phase16_processed_image",
            )
    return assets


def phase_a_assets(assets: dict[str, AnalysisAsset]) -> list[AnalysisAsset]:
    labels = [
        "front_original",
        "back_original",
    ]
    return [assets[label] for label in labels if label in assets]


def phase_b_assets(assets: dict[str, AnalysisAsset], settings: dict[str, Any] | None = None) -> list[AnalysisAsset]:
    send_diagnostic = bool((settings or {}).get("send_diagnostic_images", SEND_DIAGNOSTIC_IMAGES_TO_AI))
    if not send_diagnostic:
        labels = ["front_original", "back_original"]
    else:
        labels = [
            "front_emboss_surface",
            "front_highpass_texture",
            "front_sobel_edges",
            "front_original",
        ]
        if any(label in assets for label in ("back_original", "back_emboss_surface", "back_highpass_texture", "back_sobel_edges")):
            labels.extend(["back_emboss_surface", "back_highpass_texture", "back_sobel_edges", "back_original"])
    selected = [assets[label] for label in labels if label in assets]
    return selected


def preprocessing_context(preprocessing: dict[str, Any]) -> dict[str, Any]:
    sides = preprocessing.get("sides", {})
    return {
        side: {
            "status": payload.get("status"),
            "warnings": payload.get("warnings", []),
            "card_boundary": payload.get("card_boundary", {}),
            "centering": payload.get("centering", {}),
            "generated_images": payload.get("generated_images", {}),
        }
        for side, payload in sides.items()
    }


def card_metadata(owned_card: OwnedCard, card: Card) -> dict[str, Any]:
    return {
        "owned_card_id": owned_card.id,
        "card_id": card.id,
        "name": card.name,
        "set_name": card.set_name,
        "set_code": card.set_code,
        "card_number": card.card_number,
        "language": card.language,
        "rarity": card.rarity,
        "variant": card.variant,
        "copy_label": owned_card.copy_label,
    }


def phase_a_prompt(owned_card: OwnedCard, card: Card, preprocessing: dict[str, Any]) -> str:
    return f"""You are CardGrader AI Phase A.

You are analyzing the card's original color images and deterministic OpenCV centering data.

This is not the final grade.

Your task is to create internal working notes for the next grading phase.

Focus only on:
- visual baseline condition
- centering interpretation
- obvious corner issues
- obvious edge whitening
- obvious dents or bends visible in the original image
- print defects visible in the original image
- photo quality limitations

Do not make final grading conclusions yet.
Do not over-analyze surface scratches from diagnostic filters because they will be provided in Phase B.

Use the OpenCV centering JSON as the primary source for centering.
If the image visually disagrees with the centering JSON, mention it as a warning.

Card metadata:
{json.dumps(card_metadata(owned_card, card), ensure_ascii=False)}

Deterministic preprocessing and centering data:
{json.dumps(preprocessing_context(preprocessing), ensure_ascii=False)}

Return JSON only:

{{
  "phase": "visual_baseline",
  "status": "completed",
  "working_notes": "",
  "centering_interpretation": "",
  "visible_corner_notes": "",
  "visible_edge_notes": "",
  "obvious_surface_or_print_notes": "",
  "image_limitations": [],
  "detected_risks": [],
  "recommended_phase_b_focus": []
}}"""


def phase_b_prompt(
    owned_card: OwnedCard,
    card: Card,
    preprocessing: dict[str, Any],
    phase_a_result: dict[str, Any],
) -> str:
    return f"""You are CardGrader AI Phase B.

You are producing the final grading result.

You receive:
- Phase A working notes
- original images
- OpenCV centering JSON
- diagnostic processed images such as emboss, high-pass, Sobel, Canny, and centering debug views

Important:
Diagnostic processed images may exaggerate texture, reflections, print patterns, and noise.
Use them as defect discovery aids, not absolute proof.
When possible, confirm important defects against the original image.
Centering should primarily follow the deterministic OpenCV centering JSON.
All score fields must be numeric. Use a 1.0 to 10.0 grading scale.
Do not put "NM", "Mint", "PSA 9", or text inside score fields.
Put text labels only into label fields.
If uncertain, provide the best numeric estimate and lower confidence.
Overall score should be a numeric estimate, not a condition label.

IMPORTANT NUMERIC OUTPUT RULES:
- overall_score must be a number, example: 8.5
- confidence must be a number between 0 and 1
- subgrades.centering.score must be a number
- subgrades.corners.score must be a number
- subgrades.edges.score must be a number
- subgrades.surface.score must be a number
- textual conditions like NM, Mint, Near Mint, Gem Mint must only appear in label fields

Focus on:
- surface scratches
- holo scratches
- dents
- impressions
- print lines
- texture irregularities
- edge whitening
- corner wear
- consistency between original and diagnostic images
- final grade estimate
- risk and confidence

Card metadata:
{json.dumps(card_metadata(owned_card, card), ensure_ascii=False)}

Phase A working notes:
{json.dumps(phase_a_result, ensure_ascii=False)}

Deterministic preprocessing and centering data:
{json.dumps(preprocessing_context(preprocessing), ensure_ascii=False)}

Return JSON only:

{{
  "overall_score": 9.0,
  "estimated_grade_label": "Near Mint",
  "grade_range": {{
    "min": 9.0,
    "max": 9.0,
    "label": "9.0 - 9.0"
  }},
  "confidence": 0.0,
  "subgrades": {{
    "centering": {{
      "score": 9.0,
      "label": "Near Mint",
      "reason": ""
    }},
    "corners": {{
      "score": 9.0,
      "label": "Near Mint",
      "reason": ""
    }},
    "edges": {{
      "score": 9.0,
      "label": "Near Mint",
      "reason": ""
    }},
    "surface": {{
      "score": 9.0,
      "label": "Near Mint",
      "reason": ""
    }}
  }},
  "surface_notes": "",
  "corner_notes": "",
  "edge_notes": "",
  "centering_notes": "",
  "risk_flags": [],
  "reasoning_summary": "",
  "recommended_action": "grade | do_not_grade | inspect_more | retake_photos",
  "photo_retake_suggestions": []
}}"""


def safe_max_tokens(requested: int, phase: str) -> int:
    if requested <= LOCAL_AI_MAX_TOKENS:
        return requested
    logger.warning(
        "%s requested max_tokens=%s but LOCAL_AI_MAX_TOKENS=%s; using %s.",
        phase,
        requested,
        LOCAL_AI_MAX_TOKENS,
        LOCAL_AI_MAX_TOKENS,
    )
    return LOCAL_AI_MAX_TOKENS


def wrap_prompt(prompt: str, settings: dict[str, Any] | None = None) -> str:
    disable_thinking = bool((settings or {}).get("disable_thinking", LOCAL_AI_DISABLE_THINKING))
    if not disable_thinking:
        return prompt
    return (
        "Do not think step by step. Do not output hidden reasoning. "
        "Return JSON only. Start with { and end with }.\n\n"
        f"{prompt}\n\n/no_think"
    )


def call_server_local_json(prompt: str, assets: list[AnalysisAsset], max_tokens: int, phase: str, settings: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    model_name = resolve_server_local_model(settings)
    token_limit = safe_max_tokens(max_tokens, phase)
    if AI_MAX_CONTEXT_TOKENS:
        logger.warning(
            "%s requested AI_MAX_CONTEXT_TOKENS=%s; OpenAI-compatible local endpoints do not expose per-request context sizing.",
            phase,
            AI_MAX_CONTEXT_TOKENS,
        )
    content: list[dict[str, Any]] = [{"type": "text", "text": wrap_prompt(prompt, settings)}]
    content.extend(image_url_for_ai(asset, phase_max_long_side(phase)) for asset in assets)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": float(settings.get("temperature", LOCAL_AI_TEMPERATURE)),
        "max_tokens": token_limit,
        "response_format": LOCAL_AI_RESPONSE_FORMAT,
        "stream": LOCAL_AI_STREAMING_ENABLED,
    }
    endpoint = f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions"
    size = payload_size_bytes(payload)
    logger.info(
        "%s AI request model=%s endpoint=%s images=%s response_format=%s payload_bytes=%s",
        phase,
        model_name,
        endpoint,
        len(assets),
        LOCAL_AI_RESPONSE_FORMAT.get("type"),
        size,
    )
    try:
        response = http_json("POST", endpoint, payload, timeout_seconds=LOCAL_AI_READ_TIMEOUT_SECONDS)
    except (BrokenPipeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": "ai_provider_connection_failed",
                "message": f"{phase} AI provider request failed: {exc}",
                "selected_model": model_name,
                "endpoint": endpoint,
                "payload_size_bytes": size,
                "images_sent": len(assets),
            },
        ) from exc
    content_text, parsed_from_reasoning = content_from_chat_response(response)
    if not content_text.strip():
        raise ValueError(f"{phase} returned empty content.")
    return extract_first_json_object(content_text), json_dumps(response), parsed_from_reasoning


def call_remote_worker_json(prompt: str, assets: list[AnalysisAsset], max_tokens: int, phase: str, settings: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    if not LOCAL_AI_WORKER_BASE_URL.strip():
        raise HTTPException(status_code=400, detail="LOCAL_AI_WORKER_BASE_URL is not configured.")
    model_name = resolve_remote_worker_model(settings)
    token_limit = max_tokens
    images = [encode_asset_for_ai(asset, phase_max_long_side(phase)) for asset in assets]
    payload = {
        "prompt": wrap_prompt(prompt, settings),
        "images": images,
        "max_tokens": token_limit,
        "response_format": "text",
        "phase": phase,
        "model_name": model_name,
        "stream": LOCAL_AI_STREAMING_ENABLED,
    }
    endpoint = f"{LOCAL_AI_WORKER_BASE_URL.rstrip('/')}/api/ai/vision-json"
    size = payload_size_bytes(payload)
    logger.info("%s remote AI request model=%s endpoint=%s images=%s response_format=text payload_bytes=%s", phase, model_name, endpoint, len(images), size)
    try:
        response = http_json(
            "POST",
            endpoint,
            payload,
            timeout_seconds=LOCAL_AI_READ_TIMEOUT_SECONDS or LOCAL_AI_TIMEOUT_SECONDS,
            headers=remote_worker_headers(),
        )
    except LocalAIHTTPError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=502,
                detail="Windows AI worker is too old for Phase 16. Update ai-worker to expose /api/ai/vision-json.",
            ) from exc
        raise
    except (BrokenPipeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": "ai_provider_connection_failed",
                "message": f"{phase} remote AI worker request failed: {exc}",
                "selected_model": model_name,
                "endpoint": endpoint,
                "payload_size_bytes": size,
                "images_sent": len(images),
            },
        ) from exc
    if not response.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={
                **response,
                "selected_model": response.get("selected_model") or response.get("model") or model_name,
                "endpoint": response.get("endpoint") or endpoint,
                "payload_size_bytes": response.get("payload_size_bytes") or size,
                "images_sent": response.get("images_sent") or len(images),
            },
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError("remote worker response did not include a JSON object result")
    return result, json_dumps(response), False


def call_phase_json(prompt: str, assets: list[AnalysisAsset], max_tokens: int, phase: str, settings: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    require_local_ai_enabled()
    if LOCAL_AI_MODE == "server_local":
        return call_server_local_json(prompt, assets, max_tokens, phase, settings)
    if LOCAL_AI_MODE == "remote_worker":
        return call_remote_worker_json(prompt, assets, max_tokens, phase, settings)
    raise HTTPException(status_code=400, detail="Local AI is disabled.")


def pipeline_model_parameters(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or {}
    return {
        "provider": LOCAL_AI_PROVIDER if LOCAL_AI_MODE != "remote_worker" else "remote_worker",
        "mode": LOCAL_AI_MODE,
        "model_name": settings.get("ai_model") or LOCAL_AI_MODEL_NAME or "auto",
        "temperature": settings.get("temperature", LOCAL_AI_TEMPERATURE),
        "phase_a_max_output_tokens": min(int(settings.get("phase_a_tokens", AI_PHASE_A_MAX_OUTPUT_TOKENS)), LOCAL_AI_MAX_TOKENS),
        "phase_b_max_output_tokens": min(int(settings.get("phase_b_tokens", AI_PHASE_B_MAX_OUTPUT_TOKENS)), LOCAL_AI_MAX_TOKENS),
        "requested_context_tokens": int(settings.get("context_tokens", AI_MAX_CONTEXT_TOKENS)),
        "send_diagnostic_images_to_ai": bool(settings.get("send_diagnostic_images", SEND_DIAGNOSTIC_IMAGES_TO_AI)),
        "disable_thinking": bool(settings.get("disable_thinking", LOCAL_AI_DISABLE_THINKING)),
        "stream": LOCAL_AI_STREAMING_ENABLED,
    }


def create_pipeline_records(session: Session, owned_card: OwnedCard, selected_model_name: str, settings: dict[str, Any]) -> tuple[AnalysisRun, AIGradingPipelineRun]:
    analysis_run = AnalysisRun(
        owned_card_id=owned_card.id,
        mode="two_phase_ai_grade",
        status="running",
        model_provider="remote_worker" if LOCAL_AI_MODE == "remote_worker" else LOCAL_AI_PROVIDER,
        model_name=selected_model_name,
        prompt_version=f"{PHASE_A_PROMPT_VERSION}+{PHASE_B_PROMPT_VERSION}",
        analysis_version=PIPELINE_VERSION,
        model_parameters_json=json.dumps({**pipeline_model_parameters(settings), "model_name": selected_model_name}, ensure_ascii=True),
        analysis_scope="full",
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    pipeline = AIGradingPipelineRun(
        owned_card_id=owned_card.id,
        analysis_run_id=analysis_run.id,
        status="running",
        phase_a_status="pending",
        phase_b_status="pending",
        model_parameters_json=json.dumps({**pipeline_model_parameters(settings), "model_name": selected_model_name}, ensure_ascii=True),
    )
    session.add(pipeline)
    session.commit()
    session.refresh(pipeline)
    return analysis_run, pipeline


def update_analysis_run_from_final(analysis_run: AnalysisRun, final_result: dict[str, Any]) -> None:
    subgrades = final_result.get("subgrades") if isinstance(final_result.get("subgrades"), dict) else {}
    analysis_run.status = "completed"
    analysis_run.overall_score = parse_grade_value(final_result.get("overall_score") or final_result.get("estimated_grade"))
    low, high, _warnings = parse_grade_range(final_result.get("grade_range"), analysis_run.overall_score)
    analysis_run.estimated_grade_low = low
    analysis_run.estimated_grade_high = high
    analysis_run.confidence_level = str(final_result.get("confidence") or "low")
    parsed_subgrades = final_result.get("parsed_subgrades") if isinstance(final_result.get("parsed_subgrades"), dict) else {}
    analysis_run.centering_score = parse_grade_value(parsed_subgrades.get("centering") or subgrades.get("centering"))
    analysis_run.corners_score = parse_grade_value(parsed_subgrades.get("corners") or subgrades.get("corners"))
    analysis_run.edges_score = parse_grade_value(parsed_subgrades.get("edges") or subgrades.get("edges"))
    analysis_run.surface_score = parse_grade_value(parsed_subgrades.get("surface") or subgrades.get("surface"))
    analysis_run.human_summary = final_result.get("reasoning_summary")
    analysis_run.recommendation = final_result.get("recommended_action")
    analysis_run.recommendation_reason = "; ".join(final_result.get("risk_flags") or [])[:500]
    analysis_run.completed_at = datetime.utcnow()


def run_phase_b(
    session: Session,
    pipeline: AIGradingPipelineRun,
    analysis_run: AnalysisRun,
    owned_card: OwnedCard,
    card: Card,
    assets: dict[str, AnalysisAsset],
    preprocessing: dict[str, Any],
    phase_a_result: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    pipeline.phase_b_status = "running"
    pipeline.updated_at = datetime.utcnow()
    session.add(pipeline)
    session.commit()

    selected_assets = phase_b_assets(assets, settings)
    if not selected_assets:
        raise ValueError("Phase B has no images to send.")
    result, raw_response, parsed_from_reasoning = call_phase_json(
        phase_b_prompt(owned_card, card, preprocessing, phase_a_result),
        selected_assets,
        min(int(settings.get("phase_b_tokens", AI_PHASE_B_MAX_OUTPUT_TOKENS)), LOCAL_AI_MAX_TOKENS),
        "Phase B",
        settings,
    )
    result = normalize_final_grading_result(result)
    result["parsed_from_reasoning_content"] = parsed_from_reasoning
    result["images_sent"] = [asset.label for asset in selected_assets]
    save_text_asset(session, analysis_run.id, "phase16_ai_phase_b_raw", "phase_b_raw_response", "phase_b_raw_response.json", raw_response)
    save_text_asset(session, analysis_run.id, "phase16_ai_phase_b_result", "phase_b_result", "phase_b_result.json", json_dumps(result))

    pipeline.phase_b_status = "completed"
    pipeline.status = "completed"
    pipeline.phase_b_result_json = json.dumps(result, ensure_ascii=False)
    pipeline.final_result_json = json.dumps(result, ensure_ascii=False)
    pipeline.updated_at = datetime.utcnow()
    pipeline.completed_at = datetime.utcnow()
    update_analysis_run_from_final(analysis_run, result)
    session.add(analysis_run)
    session.add(pipeline)
    session.commit()
    session.refresh(pipeline)
    return result


def run_two_phase_ai_grading(session: Session, owned_card_id: int) -> dict[str, Any]:
    if not ENABLE_TWO_PHASE_AI_GRADING:
        raise HTTPException(status_code=400, detail="Two-phase AI grading is disabled by ENABLE_TWO_PHASE_AI_GRADING=false.")

    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    require_local_ai_enabled()
    settings = get_ai_settings(session)
    selected_model_name = resolve_remote_worker_model(settings) if LOCAL_AI_MODE == "remote_worker" else resolve_server_local_model(settings)
    logger.info("Starting two-phase AI grading owned_card_id=%s selected_model=%s mode=%s", owned_card_id, selected_model_name, LOCAL_AI_MODE)
    preprocessing = preprocess_owned_card(session, owned_card_id) if ENABLE_IMAGE_PREPROCESSING else processed_payload(session, owned_card_id)
    analysis_run, pipeline = create_pipeline_records(session, owned_card, selected_model_name, settings)
    warnings: list[str] = []
    if not bool(settings.get("send_diagnostic_images", SEND_DIAGNOSTIC_IMAGES_TO_AI)):
        warnings.append("diagnostic_images_disabled")
    if not preprocessing.get("sides"):
        warnings.append("preprocessing_unavailable")

    try:
        assets = create_assets_for_pipeline(session, analysis_run.id, owned_card_id, preprocessing)
        phase_a_selected = phase_a_assets(assets)
        if not phase_a_selected:
            raise ValueError("Phase A has no original or normalized images to send.")

        pipeline.preprocessing_snapshot_json = json.dumps(preprocessing_context(preprocessing), ensure_ascii=True)
        pipeline.phase_a_status = "running"
        pipeline.warnings_json = json.dumps(warnings, ensure_ascii=True)
        session.add(pipeline)
        session.commit()

        phase_a_result, phase_a_raw, parsed_from_reasoning = call_phase_json(
            phase_a_prompt(owned_card, card, preprocessing),
            phase_a_selected,
            min(int(settings.get("phase_a_tokens", AI_PHASE_A_MAX_OUTPUT_TOKENS)), LOCAL_AI_MAX_TOKENS),
            "Phase A",
            settings,
        )
        phase_a_result["parsed_from_reasoning_content"] = parsed_from_reasoning
        phase_a_result["images_sent"] = [asset.label for asset in phase_a_selected]
        save_text_asset(session, analysis_run.id, "phase16_ai_phase_a_raw", "phase_a_raw_response", "phase_a_raw_response.json", phase_a_raw)
        save_text_asset(session, analysis_run.id, "phase16_ai_phase_a_result", "phase_a_result", "phase_a_result.json", json_dumps(phase_a_result))

        pipeline.phase_a_status = "completed"
        pipeline.phase_a_result_json = json.dumps(phase_a_result, ensure_ascii=False)
        pipeline.updated_at = datetime.utcnow()
        session.add(pipeline)
        session.commit()
        phase_b_result = run_phase_b(session, pipeline, analysis_run, owned_card, card, assets, preprocessing, phase_a_result, settings)

        return {
            "ok": True,
            "status": "completed",
            "analysis_run": analysis_run,
            "pipeline": pipeline_status_payload(pipeline),
            "phase_a": phase_a_result,
            "final_result": phase_b_result,
            "warnings": warnings,
            "image_payload": image_payload_metadata(list(assets.values()), owned_card, card),
        }
    except HTTPException as exc:
        pipeline.status = "failed" if pipeline.phase_a_status != "completed" else "phase_b_failed"
        if pipeline.phase_a_status != "completed":
            pipeline.phase_a_status = "failed"
            analysis_run.status = "failed"
        else:
            pipeline.phase_b_status = "failed"
            analysis_run.status = "failed"
        pipeline.error_message = json.dumps(exc.detail, ensure_ascii=False) if isinstance(exc.detail, dict) else str(exc.detail)
        analysis_run.error_message = pipeline.error_message
        analysis_run.completed_at = datetime.utcnow()
        pipeline.updated_at = datetime.utcnow()
        pipeline.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.add(pipeline)
        session.commit()
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        pipeline.status = "failed" if pipeline.phase_a_status != "completed" else "phase_b_failed"
        if pipeline.phase_a_status != "completed":
            pipeline.phase_a_status = "failed"
            analysis_run.status = "failed"
        else:
            pipeline.phase_b_status = "failed"
            analysis_run.status = "failed"
        pipeline.error_message = str(exc)
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        pipeline.updated_at = datetime.utcnow()
        pipeline.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.add(pipeline)
        session.commit()
        raise HTTPException(status_code=502, detail=f"Two-phase AI grading failed: {exc}") from exc
    except LocalAIHTTPError as exc:
        pipeline.status = "failed"
        pipeline.error_message = f"AI provider HTTP {exc.status_code}: {exc.response_body[:500]}"
        analysis_run.status = "failed"
        analysis_run.error_message = "AI provider returned an HTTP error."
        analysis_run.completed_at = datetime.utcnow()
        pipeline.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.add(pipeline)
        session.commit()
        raise HTTPException(status_code=502, detail="AI provider returned an HTTP error. Details saved in the pipeline run.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pipeline.status = "failed"
        pipeline.error_message = str(exc)
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        pipeline.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.add(pipeline)
        session.commit()
        raise HTTPException(status_code=502, detail=f"AI provider is not reachable: {exc}") from exc


def retry_phase_b(session: Session, owned_card_id: int) -> dict[str, Any]:
    pipeline = latest_pipeline_run(session, owned_card_id)
    if pipeline is None or not pipeline.phase_a_result_json:
        raise HTTPException(status_code=400, detail="No stored Phase A result exists for this card.")
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    analysis_run = session.get(AnalysisRun, pipeline.analysis_run_id) if pipeline.analysis_run_id else None
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Pipeline analysis run not found.")
    settings = get_ai_settings(session)
    selected_model_name = resolve_remote_worker_model(settings) if LOCAL_AI_MODE == "remote_worker" else resolve_server_local_model(settings)
    analysis_run.model_name = selected_model_name
    pipeline.model_parameters_json = json.dumps({**pipeline_model_parameters(settings), "model_name": selected_model_name}, ensure_ascii=True)
    preprocessing = preprocess_owned_card(session, owned_card_id) if ENABLE_IMAGE_PREPROCESSING else processed_payload(session, owned_card_id)
    assets = create_assets_for_pipeline(session, analysis_run.id, owned_card_id, preprocessing)
    phase_a_result = json_loads(pipeline.phase_a_result_json, {})
    try:
        final_result = run_phase_b(session, pipeline, analysis_run, owned_card, card, assets, preprocessing, phase_a_result, settings)
    except Exception as exc:
        pipeline.phase_b_status = "failed"
        pipeline.status = "phase_b_failed"
        pipeline.error_message = str(exc)
        pipeline.updated_at = datetime.utcnow()
        session.add(pipeline)
        session.commit()
        raise
    return {
        "ok": True,
        "status": "completed",
        "pipeline": pipeline_status_payload(pipeline),
        "final_result": final_result,
    }


def pipeline_progress_payload(pipeline: AIGradingPipelineRun | None) -> dict[str, Any]:
    if pipeline is None:
        return {
            "phase": "idle",
            "step": "not_started",
            "progress": 0,
            "status_label": "not_started",
        }
    if pipeline.status == "completed":
        return {
            "phase": "completed",
            "step": "completed",
            "progress": 100,
            "status_label": "completed",
        }
    if pipeline.status in {"failed", "phase_b_failed"}:
        return {
            "phase": "error",
            "step": "failed",
            "progress": 100 if pipeline.final_result_json else 72 if pipeline.phase_a_result_json else 34,
            "status_label": "failed",
        }
    if pipeline.phase_a_status == "running":
        return {
            "phase": "phase_a",
            "step": "visual_condition",
            "progress": 37,
            "status_label": "phase A running",
        }
    if pipeline.phase_a_status == "completed" and pipeline.phase_b_status == "running":
        return {
            "phase": "phase_b",
            "step": "defect_analysis",
            "progress": 74,
            "status_label": "phase B running",
        }
    if pipeline.phase_a_status == "completed" and pipeline.phase_b_status == "completed":
        return {
            "phase": "phase_b",
            "step": "saving_result",
            "progress": 92,
            "status_label": "saving result",
        }
    if pipeline.phase_a_status == "completed":
        return {
            "phase": "phase_b",
            "step": "surface_inspection",
            "progress": 58,
            "status_label": "phase A completed",
        }
    return {
        "phase": "phase_a",
        "step": "preprocessing",
        "progress": 18,
        "status_label": "preprocessing running",
    }


def pipeline_status_payload(pipeline: AIGradingPipelineRun | None) -> dict[str, Any]:
    if pipeline is None:
        progress = pipeline_progress_payload(None)
        return {"ok": True, "status": "not_started", **progress, "progress_state": progress}
    progress = pipeline_progress_payload(pipeline)
    return {
        "ok": True,
        "id": pipeline.id,
        "owned_card_id": pipeline.owned_card_id,
        "analysis_run_id": pipeline.analysis_run_id,
        "status": pipeline.status,
        "phase_a_status": pipeline.phase_a_status,
        "phase_b_status": pipeline.phase_b_status,
        "phase": progress["phase"],
        "step": progress["step"],
        "progress": progress["progress"],
        "status_label": progress["status_label"],
        "progress_state": progress,
        "phase_a_result": json_loads(pipeline.phase_a_result_json, None),
        "phase_b_result": json_loads(pipeline.phase_b_result_json, None),
        "final_result": json_loads(pipeline.final_result_json, None),
        "preprocessing_snapshot": json_loads(pipeline.preprocessing_snapshot_json, None),
        "model_parameters": json_loads(pipeline.model_parameters_json, None),
        "warnings": json_loads(pipeline.warnings_json, []),
        "error_message": pipeline.error_message,
        "created_at": pipeline.created_at.isoformat(),
        "updated_at": pipeline.updated_at.isoformat(),
        "completed_at": pipeline.completed_at.isoformat() if pipeline.completed_at else None,
    }


def get_pipeline_status(session: Session, owned_card_id: int) -> dict[str, Any]:
    return pipeline_status_payload(latest_pipeline_run(session, owned_card_id))


def get_pipeline_result(session: Session, owned_card_id: int) -> dict[str, Any]:
    pipeline = latest_pipeline_run(session, owned_card_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="No AI grading pipeline run exists for this card.")
    return {
        "ok": pipeline.status == "completed",
        "status": pipeline.status,
        "final_result": json_loads(pipeline.final_result_json, None),
        "pipeline": pipeline_status_payload(pipeline),
    }
