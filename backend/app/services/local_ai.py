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
    LOCAL_AI_ENABLED,
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
    with urllib.request.urlopen(request, timeout=LOCAL_AI_TIMEOUT_SECONDS) as response:
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


def test_local_ai_connection() -> dict[str, Any]:
    if not LOCAL_AI_ENABLED:
        return {
            "ok": False,
            "reachable": False,
            "models": [],
            "message": "Local AI is disabled.",
        }
    if not is_localhost_url(LOCAL_AI_BASE_URL):
        raise HTTPException(status_code=400, detail="LOCAL_AI_BASE_URL must be localhost.")
    if LOCAL_AI_PROVIDER.lower() == "ollama":
        return {
            "ok": False,
            "reachable": False,
            "models": [],
            "message": "Ollama provider not implemented yet.",
        }
    try:
        response = http_json("GET", f"{LOCAL_AI_BASE_URL.rstrip('/')}/models")
        models = models_from_response(response)
        return {
            "ok": True,
            "reachable": True,
            "models": models,
            "message": "Local AI server is reachable.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "models": [],
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
    statement = (
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == opencv_run_id)
        .where(AnalysisAsset.asset_type.in_(["resized_image", "crop"]))
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    )
    assets = session.exec(statement).all()
    priority = {label: index for index, label in enumerate(ASSET_PRIORITY)}
    return sorted(
        assets,
        key=lambda asset: (
            priority.get(asset.label or "", 999),
            asset.created_at,
            asset.id or 0,
        ),
    )[:10]


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


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def extract_first_json_object(content: str) -> str:
    text = content.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
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

    return {
        **item,
        "finding_type": finding_type,
        "severity": severity,
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
    json_text = remove_trailing_commas(extract_first_json_object(content))
    return normalize_local_ai_data(json.loads(json_text))


def call_openai_compatible(prompt: str, assets: list[AnalysisAsset]) -> str:
    messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    messages_content.extend(data_url_for_asset(asset) for asset in assets)
    payload = {
        "model": LOCAL_AI_MODEL_NAME,
        "messages": [{"role": "user", "content": messages_content}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    response = http_json("POST", f"{LOCAL_AI_BASE_URL.rstrip('/')}/chat/completions", payload)
    return response["choices"][0]["message"]["content"]


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


def dry_run_local_ai(session: Session, owned_card_id: int) -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        raise HTTPException(status_code=400, detail="Run OpenCV analysis before local AI analysis.")
    assets = collect_assets(session, opencv_run.id)
    if not assets:
        raise HTTPException(status_code=400, detail="No OpenCV assets found for local AI analysis.")
    prompt = build_prompt(card, opencv_measurements(session, opencv_run))
    return {
        "config": local_ai_config(),
        "opencv_analysis_run_id": opencv_run.id,
        "images_would_send": len(assets),
        "image_labels_would_send": selected_asset_labels(assets),
        "prompt_preview": prompt,
    }


def run_local_ai_fast(session: Session, owned_card_id: int) -> dict[str, Any]:
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

    raw_response = ""
    parsed_data: dict[str, Any] | None = None
    try:
        raw_response = call_openai_compatible(build_prompt(card, opencv_measurements(session, opencv_run)), assets)
        data = parse_json_response(raw_response)
        parsed_data = data
        save_debug_artifacts(session, analysis_run.id, raw_response, parsed_data)
        save_findings(session, analysis_run, data)
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
        if raw_response:
            save_debug_artifacts(session, analysis_run.id, raw_response, parsed_data)
        analysis_run.status = "failed"
        analysis_run.error_message = f"Local AI response could not be parsed as JSON. {raw_response[:2000]}"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        raise HTTPException(status_code=502, detail="Local AI response could not be parsed as JSON.") from exc
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        raise HTTPException(status_code=502, detail=f"Local AI analysis failed: {exc}") from exc
