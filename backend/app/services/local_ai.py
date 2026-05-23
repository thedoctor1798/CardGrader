import base64
import json
import mimetypes
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import (
    LOCAL_AI_BASE_URL,
    LOCAL_AI_DISABLE_THINKING,
    LOCAL_AI_ENABLED,
    LOCAL_AI_MAX_IMAGES,
    LOCAL_AI_MAX_TOKENS,
    LOCAL_AI_MODEL_NAME,
    LOCAL_AI_PROVIDER,
    LOCAL_AI_TIMEOUT_SECONDS,
    MEDIA_DIR,
    ROOT,
)
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, Card, OwnedCard

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_AI_ANALYSIS_VERSION = "local_ai_fast_v1"
LOCAL_AI_PROMPT_VERSION = "local_vision_v1"
ASSET_PRIORITY = [
    "front_resized",
    "back_resized",
    "front_corner_tl",
    "front_corner_tr",
    "front_corner_bl",
    "front_corner_br",
    "back_corner_tl",
    "back_corner_tr",
    "back_corner_bl",
    "back_corner_br",
]
PASS_ASSET_PRIORITY = {
    "front": [
        "front_resized",
        "front_corner_tl",
        "front_corner_tr",
        "front_corner_bl",
        "front_corner_br",
        "front_edge_top",
        "front_edge_right",
        "front_edge_bottom",
        "front_edge_left",
    ],
    "back": [
        "back_resized",
        "back_corner_tl",
        "back_corner_tr",
        "back_corner_bl",
        "back_corner_br",
        "back_edge_top",
        "back_edge_right",
        "back_edge_bottom",
        "back_edge_left",
    ],
    "fast": ["front_resized", "back_resized"],
}
ALLOWED_FINDING_TYPES = {
    "corner_whitening",
    "edge_whitening",
    "scratch",
    "print_line",
    "dent",
    "stain",
    "surface_wear",
    "glare_uncertain",
    "image_quality_issue",
    "unknown",
}
ALLOWED_SEVERITIES = {"none", "very_minor", "minor", "moderate", "severe"}
ALLOWED_GRADE_IMPACTS = {"none", "low", "medium", "high"}
ALLOWED_SIDES = {"front", "back", "unknown"}


def is_localhost_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOCAL_HOSTS


def local_ai_config() -> dict[str, Any]:
    return {
        "enabled": LOCAL_AI_ENABLED,
        "provider": LOCAL_AI_PROVIDER,
        "base_url": LOCAL_AI_BASE_URL,
        "model_name": LOCAL_AI_MODEL_NAME,
        "timeout_seconds": LOCAL_AI_TIMEOUT_SECONDS,
        "max_images": LOCAL_AI_MAX_IMAGES,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
        "disable_thinking": LOCAL_AI_DISABLE_THINKING,
        "is_localhost": is_localhost_url(LOCAL_AI_BASE_URL),
    }


def require_local_ai_enabled() -> None:
    if not LOCAL_AI_ENABLED:
        raise HTTPException(status_code=400, detail="Local AI is disabled.")
    if not is_localhost_url(LOCAL_AI_BASE_URL):
        raise HTTPException(status_code=400, detail="LOCAL_AI_BASE_URL must be localhost.")
    if not LOCAL_AI_MODEL_NAME:
        raise HTTPException(status_code=400, detail="LOCAL_AI_MODEL_NAME is not configured.")
    if LOCAL_AI_PROVIDER.lower() == "ollama":
        raise HTTPException(status_code=400, detail="Ollama provider not implemented yet.")
    if LOCAL_AI_PROVIDER.lower() not in {"lmstudio", "llamacpp", "openai-compatible"}:
        raise HTTPException(status_code=400, detail="Unsupported local AI provider.")


def http_json(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise LocalAIHTTPError(exc.code, body_text) from exc


class LocalAIHTTPError(Exception):
    def __init__(self, status_code: int, response_body: str):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"Local AI HTTP {status_code}: {response_body[:500]}")


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


def test_local_ai_connection() -> dict[str, Any]:
    if not LOCAL_AI_ENABLED:
        return {
            "ok": False,
            "reachable": False,
            "models": [],
            "selected_model": LOCAL_AI_MODEL_NAME,
            "selected_model_found": False,
            "message": "Local AI is disabled.",
        }
    if not is_localhost_url(LOCAL_AI_BASE_URL):
        raise HTTPException(status_code=400, detail="LOCAL_AI_BASE_URL must be localhost.")
    if LOCAL_AI_PROVIDER.lower() == "ollama":
        return {
            "ok": False,
            "reachable": False,
            "models": [],
            "selected_model": LOCAL_AI_MODEL_NAME,
            "selected_model_found": False,
            "message": "Ollama provider not implemented yet.",
        }
    try:
        response = http_json("GET", f"{LOCAL_AI_BASE_URL.rstrip('/')}/models")
        models = models_from_response(response)
        selected_model_found = LOCAL_AI_MODEL_NAME in models
        return {
            "ok": selected_model_found if LOCAL_AI_MODEL_NAME else True,
            "reachable": True,
            "models": models,
            "selected_model": LOCAL_AI_MODEL_NAME,
            "selected_model_found": selected_model_found,
            "message": (
                "Local AI server is reachable."
                if selected_model_found or not LOCAL_AI_MODEL_NAME
                else "Local AI server is reachable, but selected model is not loaded."
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "models": [],
            "selected_model": LOCAL_AI_MODEL_NAME,
            "selected_model_found": False,
            "message": f"Local AI server is not reachable: {exc}",
        }


def local_ai_status() -> dict[str, Any]:
    base = LOCAL_AI_BASE_URL.rstrip("/")
    is_local = is_localhost_url(base)
    status = {
        "enabled": LOCAL_AI_ENABLED,
        "provider": LOCAL_AI_PROVIDER,
        "base_url": LOCAL_AI_BASE_URL,
        "model_name": LOCAL_AI_MODEL_NAME,
        "is_localhost": is_local,
        "reachable": False,
        "vision_capable": "unknown",
        "message": "Local AI is disabled.",
    }
    if not LOCAL_AI_ENABLED:
        return status
    if not is_local:
        status["message"] = "LOCAL_AI_BASE_URL must be localhost."
        return status
    if LOCAL_AI_PROVIDER.lower() == "ollama":
        status["message"] = "Ollama provider not implemented yet."
        return status

    try:
        http_json("GET", f"{base}/models")
        status["reachable"] = True
        status["message"] = "Local AI server is reachable."
    except Exception as exc:
        status["message"] = f"Local AI server is not reachable: {exc}"
    return status


def latest_completed_opencv_run(session: Session, owned_card_id: int) -> AnalysisRun | None:
    statement = (
        select(AnalysisRun)
        .where(AnalysisRun.owned_card_id == owned_card_id)
        .where(AnalysisRun.status == "completed")
        .where(AnalysisRun.mode == "local_only")
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    )
    return session.exec(statement).first()


def local_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    root = ROOT.resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid local media path.")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Local media file not found: {relative_path}")
    return path


def data_url_for_asset(asset: AnalysisAsset) -> dict[str, Any]:
    path = local_path(asset.file_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
    }


def collect_assets(session: Session, opencv_run_id: int) -> list[AnalysisAsset]:
    return collect_assets_for_pass(session, opencv_run_id, "fast")


def collect_assets_for_pass(session: Session, opencv_run_id: int, pass_type: str) -> list[AnalysisAsset]:
    statement = (
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == opencv_run_id)
        .where(AnalysisAsset.asset_type.in_(["resized_image", "crop"]))
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    )
    assets = session.exec(statement).all()
    labels = PASS_ASSET_PRIORITY.get(pass_type, ASSET_PRIORITY)
    priority = {label: index for index, label in enumerate(labels)}
    allowed = set(labels)
    assets = [asset for asset in assets if (asset.label or "") in allowed]
    return sorted(
        assets,
        key=lambda asset: (
            priority.get(asset.label or "", 999),
            asset.created_at,
            asset.id or 0,
        ),
    )[:LOCAL_AI_MAX_IMAGES]


def selected_asset_labels(assets: list[AnalysisAsset]) -> list[str]:
    return [asset.label or asset.file_path for asset in assets]


def opencv_measurements(session: Session, opencv_run: AnalysisRun) -> dict[str, Any]:
    findings = session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == opencv_run.id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()
    return {
        "analysis_run_id": opencv_run.id,
        "centering_score": opencv_run.centering_score,
        "confidence_level": opencv_run.confidence_level,
        "findings": [
            {
                "label": finding.location_label,
                "title": finding.title,
                "description": finding.description,
            }
            for finding in findings
        ],
    }


def pass_focus_text(pass_type: str) -> str:
    if pass_type == "front":
        return (
            "Only analyze front images. Do not mention the back. Do not assume back condition. "
            "Focus on front surface, front corners, front edges, print lines, scratches, dents, and holo glare uncertainty."
        )
    if pass_type == "back":
        return (
            "Only analyze back images. Do not mention the front. Do not assume front condition. "
            "Focus on whitening, back edge wear, back corner wear, dents, scratches, and stains."
        )
    return "Analyze only the images provided. Do not assume missing side condition."


def build_prompt(card: Card, measurements: dict[str, Any], pass_type: str = "fast") -> str:
    no_thinking = (
        "Do not think step by step. Do not output reasoning. Return only the final JSON object. "
        "Start with { and end with }.\n\n"
        if LOCAL_AI_DISABLE_THINKING
        else ""
    )
    suffix = "\n\n/no_think" if LOCAL_AI_DISABLE_THINKING else ""
    return f"""{no_thinking}You are a trading card condition analysis assistant.

You analyze uploaded trading card images for visible condition issues. You are not an official grading company. You must not invent flaws. Only describe issues that are visible or explicitly mark them as uncertain.

Return JSON only. Do not write markdown. Do not use code fences. Do not include prose. Do not output reasoning. Do not include explanations outside JSON. Start with {{ and end with }}.

The card metadata:
- name: {card.name}
- set: {card.set_name}
- number: {card.card_number}
- language: {card.language}

Local OpenCV measurements:
{json.dumps(measurements, ensure_ascii=False)}

Pass type: {pass_type}
Pass instructions:
{pass_focus_text(pass_type)}

Your task:
Analyze the provided images and crops:
- front/back resized images
- corner crops
- edge crops

Look for:
- corner whitening
- edge whitening
- rounded corners
- dents
- scratches
- print lines
- stains
- surface wear
- silvering
- glare/reflection uncertainty
- image quality issues

Use this strict JSON schema:
{{
  "overall_visual_condition": "string",
  "side": "front | back | unknown",
  "surface_assessment": {{
    "front": {{"summary": "string", "confidence": 0.0}},
    "back": {{"summary": "string", "confidence": 0.0}}
  }},
  "findings": [
    {{
      "image_label": "front | back | corner_tl | corner_tr | corner_bl | corner_br | edge_top | edge_right | edge_bottom | edge_left | unknown",
      "side": "front | back | unknown",
      "finding_type": "corner_whitening | edge_whitening | scratch | print_line | dent | stain | surface_wear | glare_uncertain | image_quality_issue | unknown",
      "severity": "none | very_minor | minor | moderate | severe",
      "confirmed": true,
      "uncertainty_reason": null,
      "photo_quality_issue": false,
      "confidence": 0.0,
      "location_label": "string",
      "bbox": {{"x": 0, "y": 0, "width": 0, "height": 0}},
      "title": "short finding title",
      "description": "human readable explanation",
      "grade_impact": "none | low | medium | high"
    }}
  ],
  "strengths": ["string"],
  "manual_review_recommendations": ["string"],
  "confidence_level": "low | medium | high"
}}

Rules:
- If unsure whether something is a real flaw or just glare, use finding_type "glare_uncertain".
- If no clear flaw is visible, return an empty findings list.
- Do not claim a PSA grade.
- Do not estimate market price.
- Do not mention external grading companies except in generic grading impact terms.
- Be conservative with gem mint claims.
- For tiny whitening, severity should be "very_minor" or "minor".
- Use bbox only if you can approximate the location. If not, set x/y/width/height to 0.{suffix}"""


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    return text.strip()


def extract_first_json_text(content: str) -> str:
    if not content or not content.strip():
        raise ValueError("Local AI response was empty.")
    text = strip_markdown_fences(content)
    start = text.find("{")
    if start == -1:
        raise ValueError("Local AI response did not contain JSON.")

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
    raise ValueError("Local AI response JSON object was incomplete.")


def extract_first_json_object(text: str) -> dict[str, Any]:
    json_text = remove_trailing_commas(extract_first_json_text(text))
    return json.loads(json_text)


def normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith("%"):
            try:
                return max(0.0, min(1.0, float(stripped[:-1].replace(",", ".")) / 100.0))
            except ValueError:
                return None
        try:
            value = float(stripped.replace(",", "."))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if 1.0 < numeric <= 100.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return None


def normalize_bbox(value: Any) -> dict[str, float]:
    if isinstance(value, list) and len(value) >= 4:
        value = {"x": value[0], "y": value[1], "width": value[2], "height": value[3]}
    if not isinstance(value, dict):
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    normalized = {}
    for key in ["x", "y", "width", "height"]:
        try:
            normalized[key] = float(value.get(key) or 0)
        except (TypeError, ValueError):
            normalized[key] = 0
    return normalized


def visible_issue_in_description(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "").lower() for key in ["title", "description", "location_label"])
    issue_words = [
        "visible",
        "látható",
        "whitening",
        "scratch",
        "karc",
        "dent",
        "stain",
        "wear",
        "kopás",
        "hiba",
        "sérülés",
    ]
    return any(word in text for word in issue_words)


def normalize_finding(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    finding_type = str(item.get("finding_type") or "unknown").lower()
    if finding_type not in ALLOWED_FINDING_TYPES:
        finding_type = "unknown"

    severity = str(item.get("severity") or "").lower()
    if severity not in ALLOWED_SEVERITIES:
        severity = "minor" if visible_issue_in_description(item) else "none"

    grade_impact = str(item.get("grade_impact") or "low").lower()
    if grade_impact not in ALLOWED_GRADE_IMPACTS:
        grade_impact = "low"
    side = str(item.get("side") or item.get("image_label") or item.get("location_label") or "unknown").lower()
    if side.startswith("front"):
        side = "front"
    elif side.startswith("back"):
        side = "back"
    elif side not in ALLOWED_SIDES:
        side = "unknown"
    photo_quality_issue = bool(item.get("photo_quality_issue")) or finding_type in {"glare_uncertain", "image_quality_issue"}
    confirmed = item.get("confirmed")
    if confirmed is None:
        confirmed = finding_type not in {"glare_uncertain", "image_quality_issue", "unknown"} and severity != "none"

    return {
        **item,
        "side": side,
        "finding_type": finding_type,
        "severity": severity,
        "confirmed": bool(confirmed),
        "uncertainty_reason": item.get("uncertainty_reason"),
        "photo_quality_issue": photo_quality_issue,
        "confidence": normalize_confidence(item.get("confidence")),
        "bbox": normalize_bbox(item.get("bbox")),
        "grade_impact": grade_impact,
        "location_label": item.get("location_label") or item.get("image_label") or "unknown",
    }


def normalize_local_ai_data(data: dict[str, Any]) -> dict[str, Any]:
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    normalized_findings = [finding for finding in (normalize_finding(item) for item in findings) if finding]
    confidence_level = str(data.get("confidence_level") or "low").lower()
    if confidence_level not in {"low", "medium", "high"}:
        confidence_level = "low"
    return {
        **data,
        "findings": normalized_findings,
        "confidence_level": confidence_level,
    }


def parse_json_response(content: str) -> dict[str, Any]:
    return normalize_local_ai_data(extract_first_json_object(content))


def content_from_chat_response(response: dict[str, Any]) -> tuple[str, bool]:
    message = response.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or ""
    if content.strip():
        return content, False
    reasoning_content = message.get("reasoning_content") or ""
    if reasoning_content.strip():
        return reasoning_content, True
    return "", False


def reasoning_content_from_response(response: dict[str, Any]) -> str:
    message = response.get("choices", [{}])[0].get("message", {})
    return message.get("reasoning_content") or ""


def call_openai_compatible(prompt: str, assets: list[AnalysisAsset]) -> tuple[str, str, bool]:
    messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    messages_content.extend(data_url_for_asset(asset) for asset in assets)
    payload = {
        "model": LOCAL_AI_MODEL_NAME,
        "messages": [{"role": "user", "content": messages_content}],
        "temperature": 0,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
    }
    response = http_json("POST", f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions", payload)
    content, parsed_from_reasoning_content = content_from_chat_response(response)
    return content, json.dumps(response, ensure_ascii=False, indent=2), parsed_from_reasoning_content


def call_text_only_repair(raw_output: str) -> tuple[str, str]:
    prompt = (
        "Convert the following model output into the required JSON schema. Return JSON only. "
        "Start with { and end with }.\n\n"
        f"{raw_output}"
    )
    payload = {
        "model": LOCAL_AI_MODEL_NAME,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "temperature": 0,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
    }
    response = http_json("POST", f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions", payload)
    content, _ = content_from_chat_response(response)
    return content, json.dumps(response, ensure_ascii=False, indent=2)


def parse_with_optional_repair(session: Session, analysis_run_id: int, content: str) -> tuple[dict[str, Any], str, bool]:
    try:
        extracted = extract_first_json_text(content)
        if extracted.strip() != strip_markdown_fences(content).strip():
            save_extracted_text(session, analysis_run_id, extracted)
        return normalize_local_ai_data(json.loads(remove_trailing_commas(extracted))), extracted, False
    except (json.JSONDecodeError, ValueError):
        repair_content, repair_raw = call_text_only_repair(content)
        save_repair_response(session, analysis_run_id, repair_raw)
        extracted = extract_first_json_text(repair_content)
        save_extracted_text(session, analysis_run_id, extracted)
        return normalize_local_ai_data(json.loads(remove_trailing_commas(extracted))), extracted, True


def save_text_asset(
    session: Session,
    analysis_run_id: int,
    asset_type: str,
    label: str,
    filename: str,
    content: str,
) -> AnalysisAsset:
    report_dir = MEDIA_DIR / "reports" / str(analysis_run_id)
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / filename
    path.write_text(content, encoding="utf-8")
    relative_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
    asset = AnalysisAsset(
        analysis_run_id=analysis_run_id,
        asset_type=asset_type,
        label=label,
        file_path=relative_path,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def save_debug_artifacts(session: Session, analysis_run_id: int, raw_response: str, parsed_data: dict[str, Any] | None) -> None:
    save_text_asset(
        session,
        analysis_run_id,
        "local_ai_raw_response",
        "local_ai_raw_response",
        "local_ai_raw_response.txt",
        raw_response,
    )
    if parsed_data is not None:
        save_text_asset(
            session,
            analysis_run_id,
            "local_ai_parsed_json",
            "local_ai_parsed_json",
            "local_ai_parsed.json",
            json.dumps(parsed_data, ensure_ascii=False, indent=2),
        )


def save_extracted_text(session: Session, analysis_run_id: int, content: str) -> AnalysisAsset:
    return save_text_asset(
        session,
        analysis_run_id,
        "local_ai_extracted_text",
        "local_ai_extracted_text",
        "local_ai_extracted_text.txt",
        content,
    )


def save_error_response(session: Session, analysis_run_id: int, content: str) -> AnalysisAsset:
    return save_text_asset(
        session,
        analysis_run_id,
        "local_ai_error_response",
        "local_ai_error_response",
        "local_ai_error_response.txt",
        content,
    )


def save_repair_response(session: Session, analysis_run_id: int, content: str) -> AnalysisAsset:
    return save_text_asset(
        session,
        analysis_run_id,
        "local_ai_repair_response",
        "local_ai_repair_response",
        "local_ai_repair_response.txt",
        content,
    )


def save_findings(session: Session, analysis_run: AnalysisRun, data: dict[str, Any], default_side: str = "unknown") -> None:
    for item in data.get("findings", []):
        bbox = item.get("bbox") or {}
        session.add(
            AnalysisFinding(
                analysis_run_id=analysis_run.id,
                media_id=None,
                finding_type=item.get("finding_type", "unknown"),
                severity=item.get("severity", "none"),
                confidence=item.get("confidence"),
                location_label=item.get("location_label") or item.get("image_label"),
                bbox_x=bbox.get("x") or 0,
                bbox_y=bbox.get("y") or 0,
                bbox_width=bbox.get("width") or 0,
                bbox_height=bbox.get("height") or 0,
                title=item.get("title"),
                description=item.get("description"),
                grade_impact=item.get("grade_impact"),
                side=item.get("side") or default_side,
                confirmed=item.get("confirmed"),
                uncertainty_reason=item.get("uncertainty_reason"),
                photo_quality_issue=item.get("photo_quality_issue"),
            )
        )


def dry_run_local_ai(session: Session, owned_card_id: int, pass_type: str = "fast") -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        raise HTTPException(status_code=400, detail="Run OpenCV analysis before local AI analysis.")
    if pass_type == "full":
        assets = collect_assets_for_pass(session, opencv_run.id, "front") + collect_assets_for_pass(session, opencv_run.id, "back")
    else:
        assets = collect_assets_for_pass(session, opencv_run.id, pass_type)
    if not assets:
        raise HTTPException(status_code=400, detail="No OpenCV assets found for local AI analysis.")
    prompt = build_prompt(card, opencv_measurements(session, opencv_run), pass_type)
    return {
        "config": local_ai_config(),
        "opencv_analysis_run_id": opencv_run.id,
        "images_would_send": len(assets),
        "image_labels_would_send": selected_asset_labels(assets),
        "selected_asset_file_paths": [asset.file_path for asset in assets],
        "max_images": LOCAL_AI_MAX_IMAGES,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
        "model_name": LOCAL_AI_MODEL_NAME,
        "base_url": LOCAL_AI_BASE_URL,
        "prompt_preview": prompt,
    }


def choose_single_debug_asset(assets: list[AnalysisAsset]) -> AnalysisAsset:
    return next((asset for asset in assets if asset.label == "front_resized"), assets[0])


def local_ai_debug_single_image(session: Session, owned_card_id: int) -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    require_local_ai_enabled()

    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        raise HTTPException(status_code=400, detail="Run OpenCV analysis before local AI analysis.")
    assets = collect_assets(session, opencv_run.id)
    if not assets:
        raise HTTPException(status_code=400, detail="No OpenCV assets found for local AI analysis.")
    asset = choose_single_debug_asset(assets)

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_ai_debug_single_image",
        status="running",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=LOCAL_AI_MODEL_NAME,
        prompt_version="local_vision_debug_v1",
        analysis_version="local_ai_debug_single_image_v1",
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    prompt = 'Return JSON only: {"ok": true, "summary": "string"}'
    if LOCAL_AI_DISABLE_THINKING:
        prompt = (
            "Do not think step by step. Do not output reasoning. Return only JSON. Start with { and end with }.\n"
            f"{prompt}\n/no_think"
        )
    payload = {
        "model": LOCAL_AI_MODEL_NAME,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, data_url_for_asset(asset)]}],
        "temperature": 0,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
    }
    try:
        response = http_json("POST", f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions", payload)
        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        reasoning_content = message.get("reasoning_content") or ""
        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        saved = save_text_asset(
            session,
            analysis_run.id,
            "local_ai_debug_single_image_response",
            "local_ai_debug_single_image_response",
            "local_ai_debug_single_image_response.txt",
            json.dumps(response, ensure_ascii=False, indent=2),
        )
        analysis_run.status = "completed"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        parsed_json = None
        parsed_json_success = False
        error_message = None
        try:
            parsed_json = extract_first_json_object(content or reasoning_content)
            parsed_json_success = True
        except Exception as exc:
            error_message = str(exc)
        return {
            "status": "completed",
            "model": LOCAL_AI_MODEL_NAME,
            "image_label_sent": asset.label,
            "finish_reason": finish_reason,
            "content": content,
            "reasoning_content_present": bool(reasoning_content),
            "reasoning_content_preview": reasoning_content[:1000],
            "parsed_json_success": parsed_json_success,
            "parsed_json": parsed_json,
            "error_message": error_message,
            "raw_response_asset": saved,
        }
    except LocalAIHTTPError as exc:
        saved = save_error_response(session, analysis_run.id, f"HTTP {exc.status_code}\n\n{exc.response_body}")
        analysis_run.status = "failed"
        analysis_run.error_message = "LM Studio returned an error. Details saved locally."
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        return {
            "status": "failed",
            "model": LOCAL_AI_MODEL_NAME,
            "image_label_sent": asset.label,
            "finish_reason": None,
            "content": "LM Studio hibát adott vissza. Részletek a lokális debug fájlban.",
            "reasoning_content_present": False,
            "reasoning_content_preview": "",
            "parsed_json_success": False,
            "parsed_json": None,
            "error_message": str(exc),
            "raw_response_asset": saved,
        }


def run_local_ai_pass(session: Session, owned_card_id: int, pass_type: str = "fast") -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    require_local_ai_enabled()

    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        raise HTTPException(status_code=400, detail="Run OpenCV analysis before local AI analysis.")
    assets = collect_assets_for_pass(session, opencv_run.id, pass_type)
    if not assets:
        raise HTTPException(status_code=400, detail=f"No {pass_type} OpenCV assets found for local AI analysis.")

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode=f"local_ai_{pass_type}",
        status="running",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=LOCAL_AI_MODEL_NAME,
        prompt_version=LOCAL_AI_PROMPT_VERSION,
        analysis_version=f"local_ai_{pass_type}_v1",
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    raw_response = ""
    parsed_data: dict[str, Any] | None = None
    try:
        raw_response, full_response, parsed_from_reasoning_content = call_openai_compatible(
            build_prompt(card, opencv_measurements(session, opencv_run), pass_type),
            assets,
        )
        if not raw_response.strip():
            save_debug_artifacts(session, analysis_run.id, full_response, None)
            raise ValueError("Local AI returned empty content. Try increasing LOCAL_AI_MAX_TOKENS or use a different vision model.")
        if parsed_from_reasoning_content:
            try:
                extracted = extract_first_json_text(raw_response)
                save_extracted_text(session, analysis_run.id, extracted)
                data = normalize_local_ai_data(json.loads(remove_trailing_commas(extracted)))
            except Exception as exc:
                save_debug_artifacts(session, analysis_run.id, full_response, None)
                raise ValueError("Local AI returned reasoning-only output without final JSON.") from exc
        else:
            data, _, repaired = parse_with_optional_repair(session, analysis_run.id, raw_response)
            data["repaired_from_non_json_output"] = repaired
        data["parsed_from_reasoning_content"] = parsed_from_reasoning_content
        parsed_data = data
        save_debug_artifacts(session, analysis_run.id, full_response, parsed_data)
        save_findings(session, analysis_run, data, pass_type if pass_type in {"front", "back"} else "unknown")
        analysis_run.status = "completed"
        analysis_run.human_summary = data.get("overall_visual_condition")
        analysis_run.confidence_level = data.get("confidence_level", "low")
        analysis_run.recommendation = "local_ai_findings_completed"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        findings = session.exec(
            select(AnalysisFinding)
            .where(AnalysisFinding.analysis_run_id == analysis_run.id)
            .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
        ).all()
        from .scoring import score_analysis_run

        if findings:
            from .annotations import generate_annotations
            generate_annotations(session, analysis_run.id)
        analysis_run = score_analysis_run(session, analysis_run.id)
        return {
            "analysis_run": analysis_run,
            "finding_count": len(findings),
            "images_sent": len(assets),
            "image_labels_sent": selected_asset_labels(assets),
            "status": analysis_run.status,
        }
    except (json.JSONDecodeError, ValueError) as exc:
        if raw_response and parsed_data is None:
            save_debug_artifacts(session, analysis_run.id, raw_response, parsed_data)
        analysis_run.status = "failed"
        if "reasoning-only" in str(exc):
            analysis_run.error_message = "Local AI returned reasoning-only output without final JSON."
        elif "empty content" in str(exc):
            analysis_run.error_message = str(exc)
        else:
            analysis_run.error_message = f"Local AI response could not be parsed as JSON. {raw_response[:2000]}"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        if "reasoning-only" in str(exc):
            detail = "Local AI returned reasoning-only output without final JSON."
        elif "empty content" in str(exc):
            detail = str(exc)
        else:
            detail = "A lokális modell válasza nem volt feldolgozható JSON. A debug fájlok a media/reports mappában találhatók."
        raise HTTPException(status_code=502, detail=detail) from exc
    except LocalAIHTTPError as exc:
        save_error_response(session, analysis_run.id, f"HTTP {exc.status_code}\n\n{exc.response_body}")
        analysis_run.status = "failed"
        analysis_run.error_message = "LM Studio returned an error. Details saved locally."
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        raise HTTPException(status_code=502, detail="LM Studio hibát adott vissza. Részletek a lokális debug fájlban.") from exc
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        raise HTTPException(status_code=502, detail=f"Local AI analysis failed: {exc}") from exc


def run_local_ai_fast(session: Session, owned_card_id: int) -> dict[str, Any]:
    return run_local_ai_pass(session, owned_card_id, "fast")


def latest_completed_run_by_mode(session: Session, owned_card_id: int, mode: str) -> AnalysisRun | None:
    return session.exec(
        select(AnalysisRun)
        .where(AnalysisRun.owned_card_id == owned_card_id)
        .where(AnalysisRun.mode == mode)
        .where(AnalysisRun.status == "completed")
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    ).first()


def findings_for_run(session: Session, analysis_run_id: int) -> list[AnalysisFinding]:
    return session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == analysis_run_id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()


def copy_findings_to_run(session: Session, source_findings: list[AnalysisFinding], target_run_id: int) -> None:
    for finding in source_findings:
        session.add(
            AnalysisFinding(
                analysis_run_id=target_run_id,
                media_id=finding.media_id,
                finding_type=finding.finding_type,
                severity=finding.severity,
                confidence=finding.confidence,
                location_label=finding.location_label,
                bbox_x=finding.bbox_x,
                bbox_y=finding.bbox_y,
                bbox_width=finding.bbox_width,
                bbox_height=finding.bbox_height,
                title=finding.title,
                description=finding.description,
                grade_impact=finding.grade_impact,
                side=finding.side,
                confirmed=finding.confirmed,
                uncertainty_reason=finding.uncertainty_reason,
                photo_quality_issue=finding.photo_quality_issue,
            )
        )


def run_local_ai_aggregate(session: Session, owned_card_id: int) -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    front_run = latest_completed_run_by_mode(session, owned_card_id, "local_ai_front")
    back_run = latest_completed_run_by_mode(session, owned_card_id, "local_ai_back")
    if front_run is None and back_run is None:
        raise HTTPException(status_code=400, detail="Run front or back Local AI analysis before aggregate.")

    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    centering_score = opencv_run.centering_score if opencv_run else None
    aggregate_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_ai_aggregate",
        status="completed",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=LOCAL_AI_MODEL_NAME,
        prompt_version="local_vision_aggregate_v1",
        analysis_version="local_ai_aggregate_v1",
        centering_score=centering_score,
        confidence_level="medium",
        recommendation="local_ai_aggregate_completed",
        completed_at=datetime.utcnow(),
    )
    session.add(aggregate_run)
    session.commit()
    session.refresh(aggregate_run)

    source_findings: list[AnalysisFinding] = []
    if front_run is not None:
        source_findings.extend(findings_for_run(session, front_run.id))
    if back_run is not None:
        source_findings.extend(findings_for_run(session, back_run.id))
    copy_findings_to_run(session, source_findings, aggregate_run.id)
    session.commit()

    from .scoring import score_analysis_run
    from .reporting import build_analysis_report

    aggregate_run = score_analysis_run(session, aggregate_run.id)
    return {
        "analysis_run": aggregate_run,
        "front_run_id": front_run.id if front_run else None,
        "back_run_id": back_run.id if back_run else None,
        "finding_count": len(source_findings),
        "report": build_analysis_report(session, aggregate_run.id),
    }


def pass_has_assets(session: Session, owned_card_id: int, pass_type: str) -> bool:
    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        return False
    return bool(collect_assets_for_pass(session, opencv_run.id, pass_type))


def run_local_ai_full_review(session: Session, owned_card_id: int) -> dict[str, Any]:
    front_result = run_local_ai_pass(session, owned_card_id, "front") if pass_has_assets(session, owned_card_id, "front") else None
    back_result = run_local_ai_pass(session, owned_card_id, "back") if pass_has_assets(session, owned_card_id, "back") else None
    aggregate = run_local_ai_aggregate(session, owned_card_id)
    return {
        "front": front_result,
        "back": back_result,
        "aggregate": aggregate,
    }
