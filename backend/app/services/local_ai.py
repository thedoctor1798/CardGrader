import base64
import json
import mimetypes
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
    LOCAL_AI_ENABLED,
    LOCAL_AI_MODEL_NAME,
    LOCAL_AI_PROVIDER,
    LOCAL_AI_TIMEOUT_SECONDS,
    ROOT,
)
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, Card, OwnedCard

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
LOCAL_AI_ANALYSIS_VERSION = "local_ai_fast_v1"
LOCAL_AI_PROMPT_VERSION = "local_vision_v1"


def is_localhost_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOCAL_HOSTS


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
    with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


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
    statement = (
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == opencv_run_id)
        .where(AnalysisAsset.asset_type.in_(["resized_image", "crop"]))
        .order_by(AnalysisAsset.asset_type.desc(), AnalysisAsset.created_at, AnalysisAsset.id)
    )
    return session.exec(statement).all()[:10]


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


def build_prompt(card: Card, measurements: dict[str, Any]) -> str:
    return f"""You are a trading card condition analysis assistant.

You analyze uploaded trading card images for visible condition issues. You are not an official grading company. You must not invent flaws. Only describe issues that are visible or explicitly mark them as uncertain.

Return JSON only. Do not write markdown. Do not include explanations outside JSON.

The card metadata:
- name: {card.name}
- set: {card.set_name}
- number: {card.card_number}
- language: {card.language}

Local OpenCV measurements:
{json.dumps(measurements, ensure_ascii=False)}

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
  "surface_assessment": {{
    "front": {{"summary": "string", "confidence": 0.0}},
    "back": {{"summary": "string", "confidence": 0.0}}
  }},
  "findings": [
    {{
      "image_label": "front | back | corner_tl | corner_tr | corner_bl | corner_br | edge_top | edge_right | edge_bottom | edge_left | unknown",
      "finding_type": "corner_whitening | edge_whitening | scratch | print_line | dent | stain | surface_wear | glare_uncertain | image_quality_issue | unknown",
      "severity": "none | very_minor | minor | moderate | severe",
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
- Use bbox only if you can approximate the location. If not, set x/y/width/height to 0."""


def parse_json_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Local AI response did not contain JSON.")
    return json.loads(text[start : end + 1])


def call_openai_compatible(prompt: str, assets: list[AnalysisAsset]) -> dict[str, Any]:
    messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    messages_content.extend(data_url_for_asset(asset) for asset in assets)
    payload = {
        "model": LOCAL_AI_MODEL_NAME,
        "messages": [{"role": "user", "content": messages_content}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    response = http_json("POST", f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions", payload)
    content = response["choices"][0]["message"]["content"]
    return parse_json_response(content)


def save_findings(session: Session, analysis_run: AnalysisRun, data: dict[str, Any]) -> None:
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
            )
        )


def run_local_ai_fast(session: Session, owned_card_id: int) -> AnalysisRun:
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
    assets = collect_assets(session, opencv_run.id)
    if not assets:
        raise HTTPException(status_code=400, detail="No OpenCV assets found for local AI analysis.")

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_ai_fast",
        status="running",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=LOCAL_AI_MODEL_NAME,
        prompt_version=LOCAL_AI_PROMPT_VERSION,
        analysis_version=LOCAL_AI_ANALYSIS_VERSION,
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    try:
        data = call_openai_compatible(build_prompt(card, opencv_measurements(session, opencv_run)), assets)
        save_findings(session, analysis_run, data)
        analysis_run.status = "completed"
        analysis_run.human_summary = data.get("overall_visual_condition")
        analysis_run.confidence_level = data.get("confidence_level", "low")
        analysis_run.recommendation = "local_ai_findings_completed"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        return analysis_run
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        raise HTTPException(status_code=502, detail=f"Local AI analysis failed: {exc}") from exc
