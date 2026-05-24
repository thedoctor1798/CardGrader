import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cardgrader-ai-worker")


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "").strip()
AI_WORKER_HOST = os.getenv("AI_WORKER_HOST", "0.0.0.0")
AI_WORKER_PORT = int_env("AI_WORKER_PORT", 8765)
AI_WORKER_TIMEOUT_SECONDS = int_env("AI_WORKER_TIMEOUT_SECONDS", 300)
AI_WORKER_MAX_IMAGES = max(1, min(16, int_env("AI_WORKER_MAX_IMAGES", 8)))
AI_WORKER_MAX_IMAGE_SIZE_MB = max(1, int_env("AI_WORKER_MAX_IMAGE_SIZE_MB", 8))
AI_WORKER_DISABLE_THINKING = bool_env("AI_WORKER_DISABLE_THINKING", True)
AI_WORKER_SHARED_TOKEN = os.getenv("AI_WORKER_SHARED_TOKEN", "").strip()
AI_WORKER_MAX_TOKENS = int_env("AI_WORKER_MAX_TOKENS", 4096)


class WorkerImage(BaseModel):
    label: str
    mime_type: str = "image/jpeg"
    base64: str


class GradeRequest(BaseModel):
    card_id: str | None = None
    owned_card_id: str | None = None
    card_name: str | None = None
    set_name: str | None = None
    language: str | None = None
    centering: dict[str, Any] = Field(default_factory=dict)
    images: list[WorkerImage] = Field(default_factory=list)
    grading_profile: str = "pokemon_tcg_default"


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not AI_WORKER_SHARED_TOKEN:
        return
    expected = f"Bearer {AI_WORKER_SHARED_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid AI worker token.")


def http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout_seconds: int | None = None) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds or AI_WORKER_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def models_from_response(response: dict[str, Any]) -> list[str]:
    data = response.get("data", [])
    if isinstance(data, list):
        return [
            str(item.get("id") or item.get("name"))
            for item in data
            if isinstance(item, dict) and (item.get("id") or item.get("name"))
        ]
    models = response.get("models", [])
    if isinstance(models, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in models]
    return []


def lm_studio_models() -> list[str]:
    response = http_json("GET", f"{LM_STUDIO_BASE_URL}/models", timeout_seconds=5)
    return models_from_response(response)


def selected_model() -> str:
    if LM_STUDIO_MODEL and LM_STUDIO_MODEL.lower() != "auto":
        return LM_STUDIO_MODEL
    models = lm_studio_models()
    return models[0] if models else ""


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    return text.replace("```", "").strip()


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def extract_first_json_text(content: str) -> str:
    text = strip_markdown_fences(content)
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("JSON object was incomplete.")


def parse_model_json(content: str) -> dict[str, Any]:
    return json.loads(remove_trailing_commas(extract_first_json_text(content)))


def response_content(response: dict[str, Any]) -> str:
    message = response.get("choices", [{}])[0].get("message", {})
    return message.get("content") or message.get("reasoning_content") or ""


def validate_images(images: list[WorkerImage]) -> list[WorkerImage]:
    if not images:
        raise ValueError("At least one image is required.")
    if len(images) > AI_WORKER_MAX_IMAGES:
        raise ValueError(f"Too many images. Max allowed: {AI_WORKER_MAX_IMAGES}.")
    max_bytes = AI_WORKER_MAX_IMAGE_SIZE_MB * 1024 * 1024
    validated: list[WorkerImage] = []
    for image in images:
        try:
            decoded = base64.b64decode(image.base64, validate=True)
        except Exception as exc:
            raise ValueError(f"Image {image.label} is not valid base64.") from exc
        if len(decoded) > max_bytes:
            raise ValueError(f"Image {image.label} exceeds {AI_WORKER_MAX_IMAGE_SIZE_MB} MB.")
        if not image.mime_type.startswith("image/"):
            raise ValueError(f"Image {image.label} has unsupported mime type {image.mime_type}.")
        validated.append(image)
    return validated


def build_prompt(request: GradeRequest) -> str:
    no_thinking = (
        "Do not think step by step. Do not output reasoning. Return only the final JSON object.\n\n"
        if AI_WORKER_DISABLE_THINKING
        else ""
    )
    suffix = "\n\n/no_think" if AI_WORKER_DISABLE_THINKING else ""
    return f"""{no_thinking}You are assisting with Pokemon/TCG card condition pre-grading.

You are not an official grading company. Use only the supplied images and centering metrics. Do not invent defects that are not visible. If an issue is uncertain because of glare, blur, or photo quality, mention that uncertainty in the description.

Card metadata:
- card_id: {request.card_id}
- name: {request.card_name}
- set: {request.set_name}
- language: {request.language}
- grading_profile: {request.grading_profile}

OpenCV/manual centering metrics are more reliable than visual guessing:
{json.dumps(request.centering, ensure_ascii=False)}

Evaluate:
- front centering
- back centering
- corners
- edges
- surface
- whitening
- scratches
- dents
- print lines
- holo scratches if visible

Return JSON only. Do not write markdown. Start with {{ and end with }}.

Use this exact JSON shape:
{{
  "estimated_grade": 8.5,
  "grade_range": {{"low": 8, "high": 9}},
  "confidence": "low | medium | high",
  "subscores": {{
    "centering": 9,
    "corners": 8,
    "edges": 8,
    "surface": 8
  }},
  "detected_issues": [
    {{
      "area": "back_top_left_corner",
      "severity": "very_minor | minor | moderate | severe",
      "description": "Small whitening visible on corner."
    }}
  ],
  "summary": "Likely near mint, but minor whitening limits upside.",
  "psa_10_risk": "low | medium | high",
  "recommended_action": "grade_candidate | review_manually_before_grading | do_not_grade"
}}{suffix}"""


def lm_studio_payload(request: GradeRequest, model: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": build_prompt(request)}]
    for image in request.images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.mime_type};base64,{image.base64}"},
            }
        )
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": AI_WORKER_MAX_TOKENS,
    }


from fastapi import FastAPI

app = FastAPI(title="CardGrader AI Worker")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        models = lm_studio_models()
        model = selected_model()
        reachable = True
    except Exception as exc:
        logger.warning("LM Studio health check failed: %s", exc)
        models = []
        model = LM_STUDIO_MODEL if LM_STUDIO_MODEL and LM_STUDIO_MODEL.lower() != "auto" else None
        reachable = False
    return {
        "ok": True,
        "service": "cardgrader-ai-worker",
        "lm_studio_reachable": reachable,
        "model_name": model,
        "models": models[:20],
    }


@app.post("/api/ai/grade")
def grade_card(request: GradeRequest, _: None = Depends(require_token)) -> JSONResponse:
    started = time.perf_counter()
    logger.info("Grade request received card_id=%s images=%s", request.card_id, len(request.images))
    try:
        request.images = validate_images(request.images)
    except ValueError as exc:
        logger.warning("Grade request validation failed: %s", exc)
        return JSONResponse({"ok": False, "error": "invalid_request", "message": str(exc)})

    try:
        model = selected_model()
        if not model:
            return JSONResponse({"ok": False, "error": "model_not_found", "message": "No LM Studio model is loaded."})
    except Exception as exc:
        logger.warning("LM Studio is not reachable: %s", exc)
        return JSONResponse(
            {
                "ok": False,
                "error": "lm_studio_unreachable",
                "message": "LM Studio is not reachable on the Windows client.",
            }
        )

    try:
        lm_payload = lm_studio_payload(request, model)
        response = http_json("POST", f"{LM_STUDIO_BASE_URL}/chat/completions", lm_payload)
        duration = round(time.perf_counter() - started, 2)
        raw_content = response_content(response)
        try:
            parsed = parse_model_json(raw_content)
        except Exception as exc:
            logger.warning("Model response JSON parse failed after %.2fs: %s", duration, exc)
            return JSONResponse(
                {
                    "ok": False,
                    "error": "model_response_not_valid_json",
                    "raw_response_preview": raw_content[:1000],
                }
            )
        logger.info("Grade request completed in %.2fs parse=ok", duration)
        return JSONResponse(
            {
                "ok": True,
                "result": parsed,
                "model": model,
                "duration_seconds": duration,
                "raw_response_preview": raw_content[:500],
            }
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("LM Studio returned HTTP %s", exc.code)
        return JSONResponse(
            {
                "ok": False,
                "error": "lm_studio_http_error",
                "message": f"LM Studio returned HTTP {exc.code}.",
                "raw_response_preview": body[:1000],
            }
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("LM Studio call failed: %s", exc)
        return JSONResponse(
            {
                "ok": False,
                "error": "lm_studio_unreachable",
                "message": "LM Studio is not reachable or timed out.",
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=AI_WORKER_HOST, port=AI_WORKER_PORT, log_level="info")
