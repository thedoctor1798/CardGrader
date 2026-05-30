import base64
import hashlib
import json
import logging
import mimetypes
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select

from ..config import (
    AI_WORKER_SHARED_TOKEN,
    LOCAL_AI_BASE_URL,
    LOCAL_AI_CONNECT_TIMEOUT_SECONDS,
    LOCAL_AI_DISABLE_THINKING,
    LOCAL_AI_ENABLED,
    LOCAL_AI_MAX_IMAGES,
    LOCAL_AI_MAX_TOKENS,
    LOCAL_AI_MODE,
    LOCAL_AI_MODEL_NAME,
    LOCAL_AI_PROVIDER,
    LOCAL_AI_READ_TIMEOUT_SECONDS,
    LOCAL_AI_STREAMING_ENABLED,
    LOCAL_AI_TIMEOUT_SECONDS,
    LOCAL_AI_WORKER_BASE_URL,
    MEDIA_DIR,
    ROOT,
)
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, Card, CenteringMeasurement, OwnedCard

logger = logging.getLogger(__name__)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_AI_ANALYSIS_VERSION = "local_ai_fast_v1"
LOCAL_AI_PROMPT_VERSION = "local_vision_v2_evidence_guarded"
LOCAL_AI_TEMPERATURE = 0.1
LOCAL_AI_RESPONSE_FORMAT = {"type": "json_object"}
ASSET_PRIORITY = [
    "front_resized",
    "back_resized",
]
PASS_ASSET_PRIORITY = {
    "front": [
        "front_resized",
    ],
    "back": [
        "back_resized",
    ],
    "fast": ["front_resized", "back_resized"],
}
REMOTE_WORKER_ASSET_PRIORITY = [
    "front_resized",
    "back_resized",
    "front_normalized",
    "back_normalized",
    "front_corner_tl",
    "front_corner_tr",
    "front_corner_bl",
    "front_corner_br",
    "back_corner_tl",
    "back_corner_tr",
    "back_corner_bl",
    "back_corner_br",
    "front_edge_top",
    "front_edge_right",
    "front_edge_bottom",
    "front_edge_left",
    "back_edge_top",
    "back_edge_right",
    "back_edge_bottom",
    "back_edge_left",
]
REMOTE_WORKER_LABELS = {
    "front_resized": "front_full",
    "back_resized": "back_full",
    "front_normalized": "front_full",
    "back_normalized": "back_full",
    "front_corner_tl": "front_top_left_corner",
    "front_corner_tr": "front_top_right_corner",
    "front_corner_bl": "front_bottom_left_corner",
    "front_corner_br": "front_bottom_right_corner",
    "back_corner_tl": "back_top_left_corner",
    "back_corner_tr": "back_top_right_corner",
    "back_corner_bl": "back_bottom_left_corner",
    "back_corner_br": "back_bottom_right_corner",
    "front_edge_top": "front_top_edge",
    "front_edge_right": "front_right_edge",
    "front_edge_bottom": "front_bottom_edge",
    "front_edge_left": "front_left_edge",
    "back_edge_top": "back_top_edge",
    "back_edge_right": "back_right_edge",
    "back_edge_bottom": "back_bottom_edge",
    "back_edge_left": "back_left_edge",
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
VISION_MODEL_PREFERENCES = [
    "qwen/qwen3-vl-30b",
    "qwen/qwen3-vl-8b",
    "qwen/qwen2.5-vl-7b",
]


def is_localhost_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOCAL_HOSTS


def local_ai_config() -> dict[str, Any]:
    return active_local_ai_provider().config()


def require_local_ai_enabled() -> None:
    active_local_ai_provider().require_ready()


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        logger.info("AI HTTP %s %s payload_bytes=%s", method, url, len(data))
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds or LOCAL_AI_READ_TIMEOUT_SECONDS or LOCAL_AI_TIMEOUT_SECONDS) as response:
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


def select_preferred_vision_model(models: list[str]) -> str:
    if not models:
        return ""
    normalized = [(model, model.lower()) for model in models]
    for preference in VISION_MODEL_PREFERENCES:
        for model, lowered in normalized:
            if preference in lowered:
                return model
    for model, lowered in normalized:
        if "vl" in lowered:
            return model
    for model, lowered in normalized:
        if "vision" in lowered:
            return model
    return models[0]


class LocalAIProvider:
    mode = "disabled"
    server_role = "server_app"
    client_role = "none"

    @property
    def base_url(self) -> str:
        return LOCAL_AI_BASE_URL

    @property
    def worker_base_url(self) -> str | None:
        return LOCAL_AI_WORKER_BASE_URL.strip() or None

    @property
    def is_localhost(self) -> bool:
        return is_localhost_url(self.base_url)

    def config(self) -> dict[str, Any]:
        model_name = LOCAL_AI_MODEL_NAME
        if not model_name and self.mode == "server_local":
            try:
                model_name = self.selected_model_name()
            except Exception:
                model_name = ""
        return {
            "mode": self.mode,
            "enabled": LOCAL_AI_ENABLED,
            "provider": LOCAL_AI_PROVIDER,
            "base_url": self.base_url,
            "worker_base_url": self.worker_base_url,
            "model_name": model_name or "auto",
            "timeout_seconds": LOCAL_AI_TIMEOUT_SECONDS,
            "max_images": LOCAL_AI_MAX_IMAGES,
            "max_tokens": LOCAL_AI_MAX_TOKENS,
            "disable_thinking": LOCAL_AI_DISABLE_THINKING,
            "is_localhost": self.is_localhost,
            "server_role": self.server_role,
            "client_role": self.client_role,
        }

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": LOCAL_AI_ENABLED,
            "provider": LOCAL_AI_PROVIDER,
            "base_url": self.base_url,
            "worker_base_url": self.worker_base_url,
            "model_name": LOCAL_AI_MODEL_NAME or "auto",
            "is_localhost": self.is_localhost,
            "reachable": False,
            "worker_reachable": False,
            "vision_capable": "unknown",
            "server_role": self.server_role,
            "client_role": self.client_role,
            "message": "Local AI is disabled.",
        }

    def test_connection(self) -> dict[str, Any]:
        return {
            "ok": False,
            "reachable": False,
            "mode": self.mode,
            "worker_reachable": False,
            "models": [],
            "selected_model": LOCAL_AI_MODEL_NAME or "auto",
            "selected_model_found": False,
            "message": "Local AI is disabled.",
        }

    def require_ready(self) -> None:
        raise HTTPException(status_code=400, detail="Local AI is disabled.")

    def selected_model_name(self) -> str:
        return LOCAL_AI_MODEL_NAME

    def call_chat(self, prompt: str, assets: list[AnalysisAsset]) -> tuple[str, str, bool]:
        raise HTTPException(status_code=400, detail="Local AI is disabled.")

    def call_text_repair(self, raw_output: str) -> tuple[str, str]:
        raise HTTPException(status_code=400, detail="Local AI is disabled.")


class LMStudioDirectProvider(LocalAIProvider):
    mode = "server_local"
    server_role = "backend_host_with_local_model_access"
    client_role = "same_machine_lm_studio"

    def _unsupported_provider_message(self) -> str | None:
        provider = LOCAL_AI_PROVIDER.lower()
        if provider == "ollama":
            return "Ollama provider not implemented yet."
        if provider not in {"lmstudio", "llamacpp", "openai-compatible"}:
            return "Unsupported local AI provider."
        return None

    def require_ready(self) -> None:
        if not LOCAL_AI_ENABLED:
            raise HTTPException(status_code=400, detail="Local AI is disabled.")
        if not self.is_localhost:
            raise HTTPException(status_code=400, detail="LOCAL_AI_BASE_URL must be localhost in server_local mode.")
        unsupported_message = self._unsupported_provider_message()
        if unsupported_message:
            raise HTTPException(status_code=400, detail=unsupported_message)
        if not self.selected_model_name():
            raise HTTPException(status_code=400, detail="No local vision model is loaded or configured.")

    def selected_model_name(self) -> str:
        if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
            return LOCAL_AI_MODEL_NAME
        response = http_json("GET", f"{self.base_url.rstrip('/')}/models", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS)
        return select_preferred_vision_model(models_from_response(response))

    def test_connection(self) -> dict[str, Any]:
        if not LOCAL_AI_ENABLED:
            return super().test_connection()
        unsupported_message = self._unsupported_provider_message()
        if unsupported_message:
            return {
                "ok": False,
                "reachable": False,
                "mode": self.mode,
                "worker_reachable": False,
                "models": [],
                "selected_model": LOCAL_AI_MODEL_NAME or "auto",
                "selected_model_found": False,
                "message": unsupported_message,
            }
        if not self.is_localhost:
            raise HTTPException(status_code=400, detail="LOCAL_AI_BASE_URL must be localhost in server_local mode.")
        try:
            response = http_json("GET", f"{self.base_url.rstrip('/')}/models", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS)
            models = models_from_response(response)
            if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
                selected_model = LOCAL_AI_MODEL_NAME
                selected_model_found = selected_model in models
            else:
                selected_model = select_preferred_vision_model(models)
                selected_model_found = bool(selected_model)
            return {
                "ok": selected_model_found,
                "reachable": True,
                "mode": self.mode,
                "worker_reachable": True,
                "models": models,
                "selected_model": selected_model,
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
                "mode": self.mode,
                "worker_reachable": False,
                "models": [],
                "selected_model": LOCAL_AI_MODEL_NAME or "auto",
                "selected_model_found": False,
                "message": f"Local AI server is not reachable: {exc}",
            }

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["message"] = "Local AI is disabled."
        if not LOCAL_AI_ENABLED:
            return status
        status["message"] = "Local AI server_local mode is configured."
        unsupported_message = self._unsupported_provider_message()
        if unsupported_message:
            status["message"] = unsupported_message
            return status
        if not self.is_localhost:
            status["message"] = "LOCAL_AI_BASE_URL must be localhost in server_local mode."
            return status

        try:
            response = http_json("GET", f"{self.base_url.rstrip('/')}/models", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS)
            models = models_from_response(response)
            selected_model = LOCAL_AI_MODEL_NAME if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto" else select_preferred_vision_model(models)
            status["reachable"] = True
            status["worker_reachable"] = True
            status["model_name"] = selected_model or "auto"
            status["message"] = "Local AI server is reachable."
        except Exception as exc:
            status["message"] = f"Local AI server is not reachable: {exc}"
        return status

    def call_chat(self, prompt: str, assets: list[AnalysisAsset]) -> tuple[str, str, bool]:
        model_name = self.selected_model_name()
        if not model_name:
            raise HTTPException(status_code=400, detail="No local vision model is loaded or configured.")
        logger.info("Local AI request model=%s endpoint=%s images=%s", model_name, f"{self.base_url.rstrip('/')}/chat/completions", len(assets))
        messages_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        messages_content.extend(data_url_for_asset(asset) for asset in assets)
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": messages_content}],
            "temperature": LOCAL_AI_TEMPERATURE,
            "max_tokens": LOCAL_AI_MAX_TOKENS,
            "response_format": LOCAL_AI_RESPONSE_FORMAT,
            "stream": LOCAL_AI_STREAMING_ENABLED,
        }
        response = http_json("POST", f"{self.base_url.rstrip('/')}/chat/completions", payload)
        content, parsed_from_reasoning_content = content_from_chat_response(response)
        return content, json.dumps(response, ensure_ascii=False, indent=2), parsed_from_reasoning_content

    def call_text_repair(self, raw_output: str) -> tuple[str, str]:
        model_name = self.selected_model_name()
        if not model_name:
            raise HTTPException(status_code=400, detail="No local vision model is loaded or configured.")
        prompt = (
            "Convert the following model output into the required JSON schema. Return JSON only. "
            "Start with { and end with }.\n\n"
            f"{raw_output}"
        )
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "temperature": LOCAL_AI_TEMPERATURE,
            "max_tokens": LOCAL_AI_MAX_TOKENS,
            "response_format": LOCAL_AI_RESPONSE_FORMAT,
            "stream": LOCAL_AI_STREAMING_ENABLED,
        }
        response = http_json("POST", f"{self.base_url.rstrip('/')}/chat/completions", payload)
        content, _ = content_from_chat_response(response)
        return content, json.dumps(response, ensure_ascii=False, indent=2)


class RemoteWorkerProvider(LocalAIProvider):
    mode = "remote_worker"
    server_role = "server_hosted_app"
    client_role = "gamer_pc_local_ai_worker"

    @property
    def base_url(self) -> str:
        return self.worker_base_url or ""

    @property
    def is_localhost(self) -> bool:
        return is_localhost_url(self.base_url) if self.base_url else False

    def config(self) -> dict[str, Any]:
        config = super().config()
        config["provider"] = "remote_worker"
        if LOCAL_AI_ENABLED and self.worker_base_url:
            try:
                config["model_name"] = self.selected_model_name()
            except Exception:
                config["model_name"] = LOCAL_AI_MODEL_NAME or "auto"
        return config

    def _worker_status(self) -> dict[str, Any]:
        if not self.worker_base_url:
            raise ValueError("LOCAL_AI_WORKER_BASE_URL is not configured.")
        base = self.worker_base_url.rstrip("/")
        last_error: Exception | None = None
        for path in ["/health", "/api/health", "/api/local-ai/status"]:
            try:
                return http_json("GET", f"{base}{path}", timeout_seconds=LOCAL_AI_CONNECT_TIMEOUT_SECONDS, headers=remote_worker_headers())
            except LocalAIHTTPError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                break
        raise ValueError(f"Remote Local AI worker is not reachable: {last_error}")

    def selected_model_name(self) -> str:
        if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
            return LOCAL_AI_MODEL_NAME
        worker_status = self._worker_status()
        model = str(worker_status.get("model_name") or worker_status.get("model") or "").strip()
        if model:
            return model
        raw_models = worker_status.get("models")
        models = [str(item) for item in raw_models] if isinstance(raw_models, list) else []
        return select_preferred_vision_model(models)

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["provider"] = "remote_worker"
        status["message"] = "Remote Local AI worker mode is configured."
        if not LOCAL_AI_ENABLED:
            status["message"] = "Local AI is disabled."
            return status
        if not self.worker_base_url:
            status["message"] = "LOCAL_AI_WORKER_BASE_URL is not configured."
            return status
        try:
            worker_status = self._worker_status()
            worker_model = worker_status.get("model_name") or worker_status.get("model") or LOCAL_AI_MODEL_NAME
            raw_models = worker_status.get("models")
            models = [str(item) for item in raw_models] if isinstance(raw_models, list) else ([str(worker_model)] if worker_model else [])
            selected_model = (
                LOCAL_AI_MODEL_NAME
                if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto"
                else select_preferred_vision_model(models) or str(worker_model or "")
            )
            status["reachable"] = True
            status["worker_reachable"] = True
            status["model_name"] = selected_model or "auto"
            status["vision_capable"] = str(worker_status.get("vision_capable") or "unknown")
            if worker_status.get("lm_studio_reachable") is False:
                status["message"] = "Remote AI worker is reachable, but LM Studio is not reachable on the Windows client."
            else:
                status["message"] = "Remote Local AI worker is reachable over the configured URL."
        except Exception as exc:
            status["message"] = str(exc)
        return status

    def test_connection(self) -> dict[str, Any]:
        if not LOCAL_AI_ENABLED:
            return super().test_connection()
        try:
            worker_status = self._worker_status()
            model = str(worker_status.get("model_name") or worker_status.get("model") or LOCAL_AI_MODEL_NAME or "")
            raw_models = worker_status.get("models")
            models = [str(item) for item in raw_models] if isinstance(raw_models, list) else ([model] if model else [])
            if LOCAL_AI_MODEL_NAME and LOCAL_AI_MODEL_NAME.lower() != "auto":
                selected_model = LOCAL_AI_MODEL_NAME
                selected_model_found = LOCAL_AI_MODEL_NAME in models or LOCAL_AI_MODEL_NAME == model
            else:
                selected_model = select_preferred_vision_model(models) or model
                selected_model_found = bool(selected_model)
            lm_studio_reachable = worker_status.get("lm_studio_reachable") is not False
            return {
                "ok": selected_model_found and lm_studio_reachable,
                "reachable": True,
                "mode": self.mode,
                "worker_reachable": True,
                "models": models,
                "selected_model": selected_model or "auto",
                "selected_model_found": selected_model_found,
                "message": (
                    "Remote Local AI worker is reachable."
                    if lm_studio_reachable
                    else "Remote AI worker is reachable, but LM Studio is not reachable on the Windows client."
                ),
            }
        except Exception as exc:
            return {
                "ok": False,
                "reachable": False,
                "mode": self.mode,
                "worker_reachable": False,
                "models": [],
                "selected_model": LOCAL_AI_MODEL_NAME or "auto",
                "selected_model_found": False,
                "message": str(exc),
            }

    def require_ready(self) -> None:
        if not LOCAL_AI_ENABLED:
            raise HTTPException(status_code=400, detail="Local AI is disabled.")
        if not self.worker_base_url:
            raise HTTPException(status_code=400, detail="LOCAL_AI_WORKER_BASE_URL is not configured.")
        try:
            self._worker_status()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Remote Local AI worker is not reachable: {exc}") from exc

    def call_chat(self, prompt: str, assets: list[AnalysisAsset]) -> tuple[str, str, bool]:
        payload = {
            "card_id": None,
            "card_name": "CardGrader remote worker legacy analysis",
            "set_name": None,
            "language": None,
            "centering": {"backend_prompt_preview": prompt[:2000]},
            "images": [remote_worker_image_payload(asset) for asset in assets[:LOCAL_AI_MAX_IMAGES]],
            "grading_profile": "pokemon_tcg_default",
        }
        worker_response = remote_ai_grade_http(payload)
        content = json.dumps(worker_response.get("result") or worker_response, ensure_ascii=False)
        return content, json.dumps(worker_response, ensure_ascii=False, indent=2), False

    def call_text_repair(self, raw_output: str) -> tuple[str, str]:
        return raw_output, raw_output


def active_local_ai_provider() -> LocalAIProvider:
    if LOCAL_AI_MODE == "server_local":
        return LMStudioDirectProvider()
    if LOCAL_AI_MODE == "remote_worker":
        return RemoteWorkerProvider()
    return LocalAIProvider()


def remote_worker_headers() -> dict[str, str]:
    if not AI_WORKER_SHARED_TOKEN:
        return {}
    return {"Authorization": f"Bearer {AI_WORKER_SHARED_TOKEN}"}


def test_local_ai_connection() -> dict[str, Any]:
    return active_local_ai_provider().test_connection()


def local_ai_status() -> dict[str, Any]:
    return active_local_ai_provider().status()


def effective_local_ai_model_name() -> str:
    try:
        return active_local_ai_provider().selected_model_name() or LOCAL_AI_MODEL_NAME or "auto"
    except Exception:
        return LOCAL_AI_MODEL_NAME or "auto"


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
        .where(AnalysisAsset.asset_type == "resized_image")
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


def image_payload_metadata_for_asset(asset: AnalysisAsset, owned_card: OwnedCard | None = None, card: Card | None = None) -> dict[str, Any]:
    path = local_path(asset.file_path)
    image_bytes = path.read_bytes()
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    width: int | None = None
    height: int | None = None
    try:
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError):
        width = None
        height = None
    relative_path = str(path)
    try:
        relative_path = str(path.relative_to(ROOT))
    except ValueError:
        pass
    return {
        "owned_card_id": owned_card.id if owned_card else None,
        "card_id": card.id if card else None,
        "media_id": None,
        "asset_id": asset.id,
        "image_label": remote_worker_label(asset),
        "asset_label": asset.label,
        "asset_type": asset.asset_type,
        "relative_path": relative_path.replace("\\", "/"),
        "filename": path.name,
        "width": width,
        "height": height,
        "mime_type": mimetypes.guess_type(path.name)[0] or "image/jpeg",
        "file_size": len(image_bytes),
        "sha256": sha256,
        "image_hash_short": sha256[:12],
    }


def image_payload_metadata(
    assets: list[AnalysisAsset],
    owned_card: OwnedCard | None = None,
    card: Card | None = None,
) -> list[dict[str, Any]]:
    return [image_payload_metadata_for_asset(asset, owned_card, card) for asset in assets]


def allowed_areas_for_assets(assets: list[AnalysisAsset]) -> list[str]:
    allowed: list[str] = []
    for asset in assets:
        label = remote_worker_label(asset)
        if label not in allowed:
            allowed.append(label)
    return allowed


def analysis_scope_for_assets(assets: list[AnalysisAsset], pass_type: str) -> str:
    if pass_type in {"front", "back", "debug_single_image"}:
        return "partial"
    allowed = set(allowed_areas_for_assets(assets))
    return "full" if {"front_full", "back_full"}.issubset(allowed) and len(assets) > 1 else "partial"


def model_parameters() -> dict[str, Any]:
    return {
        "temperature": LOCAL_AI_TEMPERATURE,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
        "response_format": LOCAL_AI_RESPONSE_FORMAT,
        "disable_thinking": LOCAL_AI_DISABLE_THINKING,
        "stream": LOCAL_AI_STREAMING_ENABLED,
    }


def set_analysis_debug_metadata(
    analysis_run: AnalysisRun,
    assets: list[AnalysisAsset],
    allowed_areas: list[str],
    warnings: list[str],
    analysis_scope: str,
    payload_metadata: list[dict[str, Any]] | None = None,
) -> None:
    analysis_run.image_labels_json = json.dumps(selected_asset_labels(assets), ensure_ascii=True)
    analysis_run.allowed_areas_json = json.dumps(allowed_areas, ensure_ascii=True)
    analysis_run.warnings_json = json.dumps(sorted(set(warnings)), ensure_ascii=True)
    analysis_run.model_parameters_json = json.dumps(model_parameters(), ensure_ascii=True)
    analysis_run.analysis_scope = analysis_scope
    analysis_run.image_payload_json = json.dumps(payload_metadata or image_payload_metadata(assets), ensure_ascii=True, default=str)


def add_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def cap_confidence_level(value: Any, max_level: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    normalized = str(value or "low").lower()
    if normalized not in order:
        normalized = "low"
    return normalized if order[normalized] <= order[max_level] else max_level


def area_side(area: str) -> str:
    if area.startswith("front_"):
        return "front"
    if area.startswith("back_"):
        return "back"
    return "unknown"


def normalize_area_name(value: Any, allowed_areas: list[str]) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in allowed_areas:
        return raw
    if raw in {"front", "front_resized", "front_normalized"} and "front_full" in allowed_areas:
        return "front_full"
    if raw in {"back", "back_resized", "back_normalized"} and "back_full" in allowed_areas:
        return "back_full"
    label_map = {
        "corner_tl": "top_left_corner",
        "corner_tr": "top_right_corner",
        "corner_bl": "bottom_left_corner",
        "corner_br": "bottom_right_corner",
        "edge_top": "top_edge",
        "edge_right": "right_edge",
        "edge_bottom": "bottom_edge",
        "edge_left": "left_edge",
    }
    if raw in label_map:
        for prefix in ("front", "back"):
            candidate = f"{prefix}_{label_map[raw]}"
            if candidate in allowed_areas:
                return candidate
    return raw or "unknown"


def visible_side_available(allowed_areas: list[str], side: str) -> bool:
    return any(area.startswith(f"{side}_") for area in allowed_areas)


def filter_local_ai_findings(
    data: dict[str, Any],
    allowed_areas: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    filtered: list[dict[str, Any]] = []
    for finding in data.get("findings", []):
        area = normalize_area_name(
            finding.get("image_label") or finding.get("location_label") or finding.get("area"),
            allowed_areas,
        )
        side = str(finding.get("side") or area_side(area) or "unknown").lower()
        if area not in allowed_areas:
            add_warning(warnings, "model_reported_issue_for_unprovided_area")
            continue
        if side in {"front", "back"} and not visible_side_available(allowed_areas, side):
            add_warning(warnings, "model_reported_issue_for_unprovided_area")
            continue
        finding["image_label"] = area
        finding["location_label"] = area
        finding["side"] = side if side in {"front", "back"} else area_side(area)
        filtered.append(finding)
    data["findings"] = filtered
    return data


def filter_remote_issues(
    issues: Any,
    allowed_areas: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(issues, list):
        return []
    filtered: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        area = normalize_area_name(issue.get("area"), allowed_areas)
        side = area_side(area)
        if area not in allowed_areas:
            add_warning(warnings, "model_reported_issue_for_unprovided_area")
            continue
        if side in {"front", "back"} and not visible_side_available(allowed_areas, side):
            add_warning(warnings, "model_reported_issue_for_unprovided_area")
            continue
        next_issue = dict(issue)
        next_issue["area"] = area
        filtered.append(next_issue)
    return filtered


def apply_grading_guardrails(
    data: dict[str, Any],
    assets: list[AnalysisAsset],
    allowed_areas: list[str],
    analysis_scope: str,
    warnings: list[str],
) -> dict[str, Any]:
    if analysis_scope == "partial" or len(assets) <= 1:
        add_warning(warnings, "limited_image_set")
        data["confidence_level"] = cap_confidence_level(data.get("confidence_level"), "medium")
    data = filter_local_ai_findings(data, allowed_areas, warnings)
    if warnings:
        data["guardrail_warnings"] = sorted(set(warnings))
    return data


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
            "Report only front-side defects that are visibly present in the provided images."
        )
    if pass_type == "back":
        return (
            "Only analyze back images. Do not mention the front. Do not assume front condition. "
            "Report only back-side defects that are visibly present in the provided images."
        )
    return "Analyze only the images provided. Do not assume missing side condition."


def build_prompt(
    card: Card,
    measurements: dict[str, Any],
    pass_type: str = "fast",
    allowed_areas: list[str] | None = None,
    image_labels: list[str] | None = None,
    analysis_scope: str = "partial",
) -> str:
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
Analysis scope: {analysis_scope}
Images attached in order:
{json.dumps(image_labels or [], ensure_ascii=False)}
Allowed issue areas:
{json.dumps(allowed_areas or [], ensure_ascii=False)}

Pass instructions:
{pass_focus_text(pass_type)}

Your task:
Analyze only the provided images. Only report visible evidence.

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
      "image_label": "one exact value from the Allowed issue areas list above",
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
- Every findings[].image_label must be exactly one of the allowed issue areas listed above.
- Only report defects that are visible in the provided image(s).
- Do not infer back-side defects from front images.
- Do not infer front-side defects from back images.
- Do not report an issue in an area if no image/crop for that area was provided.
- If no clear defect is visible, findings must be [].
- If image quality is insufficient, lower confidence instead of inventing defects.
- If only one image is provided, do not produce confident full-card conclusions; confidence_level must not be high.
- If only front image is provided, do not report back issues.
- If only back image is provided, do not report front surface/holo issues.
- Do not default to 8.5 or any grade-like conclusion.
- Do not reuse common grading phrases unless supported by visible evidence.
- Do not say whitening exists unless it is visibly present.
- If uncertain between high grades, explain the visible evidence in findings. If there is no visible evidence, keep findings empty and lower confidence.
- If unsure whether something is a real flaw or just glare, use finding_type "glare_uncertain".
- If no clear flaw is visible, return an empty findings list.
- Do not claim a PSA grade.
- Do not estimate market price.
- Do not mention external grading companies except in generic grading impact terms.
- Be conservative with gem mint claims.
- For any visible tiny defect, severity should be "very_minor" or "minor".
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
    return active_local_ai_provider().call_chat(prompt, assets)


def call_text_only_repair(raw_output: str) -> tuple[str, str]:
    return active_local_ai_provider().call_text_repair(raw_output)


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
    allowed_areas = allowed_areas_for_assets(assets)
    image_labels = selected_asset_labels(assets)
    prompt = build_prompt(
        card,
        opencv_measurements(session, opencv_run),
        pass_type,
        allowed_areas,
        image_labels,
        analysis_scope_for_assets(assets, pass_type),
    )
    config = local_ai_config()
    return {
        "config": config,
        "opencv_analysis_run_id": opencv_run.id,
        "images_would_send": len(assets),
        "image_labels_would_send": selected_asset_labels(assets),
        "image_payload_would_send": image_payload_metadata(assets, owned_card, card),
        "selected_asset_file_paths": [asset.file_path for asset in assets],
        "max_images": LOCAL_AI_MAX_IMAGES,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
        "model_name": config.get("model_name") or "",
        "base_url": config.get("base_url") or "",
        "prompt_preview": prompt,
    }


def latest_centering_for_side(session: Session, owned_card_id: int, side: str) -> CenteringMeasurement | None:
    return session.exec(
        select(CenteringMeasurement)
        .where(CenteringMeasurement.owned_card_id == owned_card_id)
        .where(CenteringMeasurement.side == side)
        .order_by(CenteringMeasurement.created_at.desc(), CenteringMeasurement.id.desc())
    ).first()


def remote_worker_centering_payload(session: Session, owned_card_id: int, opencv_run: AnalysisRun | None) -> dict[str, Any]:
    front = latest_centering_for_side(session, owned_card_id, "front")
    back = latest_centering_for_side(session, owned_card_id, "back")
    return {
        "front_left_right": front.horizontal_ratio_label if front else None,
        "front_top_bottom": front.vertical_ratio_label if front else None,
        "back_left_right": back.horizontal_ratio_label if back else None,
        "back_top_bottom": back.vertical_ratio_label if back else None,
        "front_score": front.centering_score if front else None,
        "back_score": back.centering_score if back else None,
        "opencv_centering_score": opencv_run.centering_score if opencv_run else None,
    }


def collect_remote_worker_assets(session: Session, opencv_run_id: int) -> list[AnalysisAsset]:
    assets = session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == opencv_run_id)
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    ).all()
    priority = {label: index for index, label in enumerate(REMOTE_WORKER_ASSET_PRIORITY)}
    allowed = set(priority)
    selected = [asset for asset in assets if (asset.label or "") in allowed]
    return sorted(
        selected,
        key=lambda asset: (
            priority.get(asset.label or "", 999),
            asset.created_at,
            asset.id or 0,
        ),
    )[:LOCAL_AI_MAX_IMAGES]


def remote_worker_label(asset: AnalysisAsset) -> str:
    label = asset.label or "image"
    if label in REMOTE_WORKER_LABELS:
        return REMOTE_WORKER_LABELS[label]
    return label.replace("_resized", "_full")


def remote_worker_image_payload(asset: AnalysisAsset, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    path = local_path(asset.file_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return {
        "label": remote_worker_label(asset),
        "mime_type": mime_type,
        "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        "media_id": metadata.get("media_id") if metadata else None,
        "asset_id": metadata.get("asset_id") if metadata else asset.id,
        "relative_path": metadata.get("relative_path") if metadata else str(asset.file_path),
        "filename": metadata.get("filename") if metadata else path.name,
        "width": metadata.get("width") if metadata else None,
        "height": metadata.get("height") if metadata else None,
        "file_size": metadata.get("file_size") if metadata else None,
        "sha256": metadata.get("sha256") if metadata else None,
        "image_hash_short": metadata.get("image_hash_short") if metadata else None,
    }


def remote_grade_payload(
    session: Session,
    owned_card: OwnedCard,
    card: Card,
    opencv_run: AnalysisRun | None,
    assets: list[AnalysisAsset],
    payload_metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    allowed_areas = allowed_areas_for_assets(assets)
    metadata_by_asset_id = {
        item.get("asset_id"): item
        for item in (payload_metadata or image_payload_metadata(assets, owned_card, card))
        if item.get("asset_id") is not None
    }
    return {
        "card_id": str(card.id),
        "owned_card_id": str(owned_card.id),
        "card_name": card.name,
        "set_name": card.set_name,
        "language": card.language,
        "centering": remote_worker_centering_payload(session, owned_card.id, opencv_run),
        "images": [remote_worker_image_payload(asset, metadata_by_asset_id.get(asset.id)) for asset in assets],
        "image_payload": payload_metadata or list(metadata_by_asset_id.values()),
        "allowed_areas": allowed_areas,
        "image_labels": selected_asset_labels(assets),
        "analysis_scope": analysis_scope_for_assets(assets, "remote_ai_grade"),
        "model_parameters": model_parameters(),
        "model_name": LOCAL_AI_MODEL_NAME or "auto",
        "stream": LOCAL_AI_STREAMING_ENABLED,
        "prompt_rules": [
            "Only report defects visible in the provided images.",
            "Every detected_issues[].area must be one of allowed_areas.",
            "Do not infer back defects from front images or front defects from back images.",
            "If no clear defect is visible, detected_issues must be [].",
            "Do not default to 8.5 or repeat common whitening phrases without visible evidence.",
        ],
        "grading_profile": "pokemon_tcg_default",
    }


def remote_ai_grade_http(payload: dict[str, Any]) -> dict[str, Any]:
    if LOCAL_AI_MODE != "remote_worker":
        raise HTTPException(status_code=400, detail="LOCAL_AI_MODE must be remote_worker for remote AI grading.")
    if not LOCAL_AI_WORKER_BASE_URL.strip():
        raise HTTPException(status_code=400, detail="LOCAL_AI_WORKER_BASE_URL is not configured.")
    url = f"{LOCAL_AI_WORKER_BASE_URL.rstrip('/')}/api/ai/grade"
    payload_bytes = len(json.dumps(payload).encode("utf-8"))
    print(
        "Remote AI worker request",
        {
            "url": url,
            "timeout": LOCAL_AI_TIMEOUT_SECONDS,
            "images": len(payload.get("images", [])),
            "payload_bytes": payload_bytes,
            "model": payload.get("model_name") or LOCAL_AI_MODEL_NAME or "auto",
        },
    )
    try:
        return http_json(
            "POST",
            url,
            payload,
            timeout_seconds=LOCAL_AI_TIMEOUT_SECONDS,
            headers=remote_worker_headers(),
        )
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
    except (BrokenPipeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Remote AI worker unreachable: {exc}")
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": "remote_ai_worker_unreachable",
                "message": (
                    "CardGrader backend could not reach the Windows AI worker. "
                    "Check Tailscale, worker service, firewall, and LM Studio."
                ),
                "selected_model": payload.get("model_name") or LOCAL_AI_MODEL_NAME or "auto",
                "endpoint": url,
                "payload_size_bytes": payload_bytes,
                "images_sent": len(payload.get("images", [])),
            },
        ) from exc


def score_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(10.0, numeric))


def grade_range_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def issue_side(area: str) -> str:
    if area.startswith("front"):
        return "front"
    if area.startswith("back"):
        return "back"
    return "unknown"


def issue_type(issue: dict[str, Any]) -> str:
    text = " ".join(str(issue.get(key) or "").lower() for key in ["area", "description"])
    if "whitening" in text:
        return "corner_whitening" if "corner" in text else "edge_whitening"
    if "scratch" in text:
        return "scratch"
    if "dent" in text:
        return "dent"
    if "print line" in text or "print_line" in text:
        return "print_line"
    if "stain" in text:
        return "stain"
    if "wear" in text:
        return "surface_wear"
    return "unknown"


def grade_impact_for_severity(severity: str) -> str:
    if severity in {"severe", "moderate"}:
        return "high"
    if severity == "minor":
        return "medium"
    if severity == "very_minor":
        return "low"
    return "none"


def add_template_warnings(session: Session, owned_card_id: int, issues: list[dict[str, Any]], warnings: list[str]) -> None:
    suspicious_phrases = ("minor whitening", "limits upside", "back_top_left_corner whitening")
    combined = " ".join(
        str(issue.get(key) or "").lower()
        for issue in issues
        for key in ("area", "description")
    )
    if any(phrase in combined for phrase in suspicious_phrases):
        add_warning(warnings, "repeated_template_issue_warning")
        return

    descriptions = {
        str(issue.get("description") or "").strip().lower()
        for issue in issues
        if str(issue.get("description") or "").strip()
    }
    if not descriptions:
        return
    for description in descriptions:
        existing = session.exec(
            select(AnalysisFinding, AnalysisRun)
            .join(AnalysisRun, AnalysisFinding.analysis_run_id == AnalysisRun.id)
            .where(AnalysisFinding.description == description)
            .where(AnalysisRun.owned_card_id != owned_card_id)
        ).all()
        distinct_cards = {row[1].owned_card_id for row in existing}
        if len(distinct_cards) >= 2:
            add_warning(warnings, "repeated_template_issue_warning")
            return


def add_consistency_warnings(
    result: dict[str, Any],
    opencv_run: AnalysisRun | None,
    issues: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    subscores = result.get("subscores") if isinstance(result.get("subscores"), dict) else {}
    centering_score = score_value(subscores.get("centering")) or (opencv_run.centering_score if opencv_run else None)
    estimated_grade = score_value(result.get("estimated_grade"))
    if centering_score is not None and centering_score >= 9 and estimated_grade is not None and estimated_grade < 8 and not issues:
        add_warning(warnings, "model_grade_low_without_visible_evidence")
        result["confidence"] = cap_confidence_level(result.get("confidence"), "low")


def add_stale_image_payload_warnings(
    session: Session,
    owned_card_id: int,
    payload_metadata: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    hashes = {
        str(item.get("sha256") or "")
        for item in payload_metadata
        if item.get("sha256")
    }
    if not hashes:
        return
    previous_runs = session.exec(
        select(AnalysisRun)
        .where(AnalysisRun.owned_card_id != owned_card_id)
        .where(AnalysisRun.image_payload_json.is_not(None))
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(100)
    ).all()
    for previous_run in previous_runs:
        previous_payload = parse_json_list_of_objects(previous_run.image_payload_json)
        previous_hashes = {
            str(item.get("sha256") or "")
            for item in previous_payload
            if item.get("sha256")
        }
        if hashes.intersection(previous_hashes):
            add_warning(warnings, "possible_stale_image_payload")
            return


def parse_json_list_of_objects(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def save_remote_worker_findings(session: Session, analysis_run: AnalysisRun, issues: Any) -> int:
    if not isinstance(issues, list):
        return 0
    saved = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "minor").lower()
        if severity not in ALLOWED_SEVERITIES:
            severity = "minor"
        area = str(issue.get("area") or "unknown")
        session.add(
            AnalysisFinding(
                analysis_run_id=analysis_run.id,
                media_id=None,
                finding_type=issue_type(issue),
                severity=severity,
                confidence=None,
                location_label=area,
                bbox_x=0,
                bbox_y=0,
                bbox_width=0,
                bbox_height=0,
                title=area.replace("_", " "),
                description=issue.get("description"),
                grade_impact=grade_impact_for_severity(severity),
                side=issue_side(area),
                confirmed=True,
                uncertainty_reason=None,
                photo_quality_issue=False,
            )
        )
        saved += 1
    return saved


def run_remote_ai_grade(session: Session, owned_card_id: int) -> dict[str, Any]:
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if LOCAL_AI_MODE != "remote_worker":
        raise HTTPException(status_code=400, detail="Remote AI grading requires LOCAL_AI_MODE=remote_worker.")

    opencv_run = latest_completed_opencv_run(session, owned_card_id)
    if opencv_run is None:
        raise HTTPException(status_code=400, detail="Run OpenCV analysis before remote AI grading.")
    assets = collect_remote_worker_assets(session, opencv_run.id)
    if not assets:
        raise HTTPException(status_code=400, detail="No OpenCV assets found for remote AI grading.")
    allowed_areas = allowed_areas_for_assets(assets)
    image_labels = selected_asset_labels(assets)
    analysis_scope = analysis_scope_for_assets(assets, "remote_ai_grade")
    payload_metadata = image_payload_metadata(assets, owned_card, card)
    guardrail_warnings: list[str] = []
    if analysis_scope == "partial":
        add_warning(guardrail_warnings, "limited_image_set")
    add_stale_image_payload_warnings(session, owned_card_id, payload_metadata, guardrail_warnings)
    selected_model_name = effective_local_ai_model_name()

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="remote_ai_grade",
        status="running",
        model_provider="remote_worker",
        model_name=selected_model_name,
        prompt_version="remote_worker_grade_v1",
        analysis_version="remote_ai_worker_v1",
        centering_score=opencv_run.centering_score,
        image_labels_json=json.dumps(image_labels, ensure_ascii=True),
        allowed_areas_json=json.dumps(allowed_areas, ensure_ascii=True),
        warnings_json=json.dumps(guardrail_warnings, ensure_ascii=True),
        model_parameters_json=json.dumps({**model_parameters(), "model_name": selected_model_name}, ensure_ascii=True),
        analysis_scope=analysis_scope,
        image_payload_json=json.dumps(payload_metadata, ensure_ascii=True, default=str),
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    payload = remote_grade_payload(session, owned_card, card, opencv_run, assets, payload_metadata)
    payload["model_name"] = selected_model_name
    try:
        worker_response = remote_ai_grade_http(payload)
        save_text_asset(
            session,
            analysis_run.id,
            "remote_ai_worker_response",
            "remote_ai_worker_response",
            "remote_ai_worker_response.json",
            json.dumps(worker_response, ensure_ascii=False, indent=2),
        )
        if not worker_response.get("ok"):
            analysis_run.status = "failed"
            analysis_run.error_message = str(worker_response.get("error") or "Remote AI worker returned ok=false.")
            analysis_run.completed_at = datetime.utcnow()
            session.add(analysis_run)
            session.commit()
            session.refresh(analysis_run)
            return {
                "ok": False,
                "analysis_run": analysis_run,
                "worker_result": worker_response,
                "images_sent": len(assets),
                "image_labels_sent": image_labels,
                "image_payload": payload_metadata,
                "allowed_issue_areas": allowed_areas,
                "warnings": sorted(set(guardrail_warnings)),
                "analysis_scope": analysis_scope,
            }

        result = worker_response.get("result") if isinstance(worker_response.get("result"), dict) else worker_response
        filtered_issues = filter_remote_issues(result.get("detected_issues"), allowed_areas, guardrail_warnings)
        if len(filtered_issues) != len(result.get("detected_issues") or []):
            add_warning(guardrail_warnings, "invalid_issues_filtered")
        add_template_warnings(session, owned_card_id, filtered_issues, guardrail_warnings)
        add_consistency_warnings(result, opencv_run, filtered_issues, guardrail_warnings)
        result["detected_issues"] = filtered_issues
        result["warnings"] = sorted(set([*result.get("warnings", []), *guardrail_warnings])) if isinstance(result.get("warnings"), list) else sorted(set(guardrail_warnings))
        result["analysis_scope"] = analysis_scope
        result["allowed_issue_areas"] = allowed_areas
        if analysis_scope == "partial":
            result["confidence"] = cap_confidence_level(result.get("confidence"), "medium")
        subscores = result.get("subscores") if isinstance(result.get("subscores"), dict) else {}
        grade_range = result.get("grade_range") if isinstance(result.get("grade_range"), dict) else {}
        finding_count = save_remote_worker_findings(session, analysis_run, filtered_issues)

        analysis_run.status = "completed"
        analysis_run.model_name = str(worker_response.get("model") or selected_model_name)
        if analysis_scope == "full":
            analysis_run.overall_score = score_value(result.get("estimated_grade"))
            analysis_run.estimated_grade_low = grade_range_value(grade_range.get("low"))
            analysis_run.estimated_grade_high = grade_range_value(grade_range.get("high"))
        analysis_run.confidence_level = str(result.get("confidence") or "medium").lower()
        analysis_run.centering_score = score_value(subscores.get("centering")) or analysis_run.centering_score
        if analysis_scope == "full":
            analysis_run.corners_score = score_value(subscores.get("corners"))
            analysis_run.edges_score = score_value(subscores.get("edges"))
            analysis_run.surface_score = score_value(subscores.get("surface"))
        analysis_run.human_summary = result.get("summary")
        analysis_run.recommendation = "partial_analysis" if analysis_scope == "partial" else result.get("recommended_action")
        analysis_run.recommendation_reason = (
            "Részleges elemzés, nem teljes grading."
            if analysis_scope == "partial"
            else f"PSA 10 risk: {result.get('psa_10_risk') or 'unknown'}"
        )
        set_analysis_debug_metadata(analysis_run, assets, allowed_areas, guardrail_warnings, analysis_scope, payload_metadata)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        return {
            "ok": True,
            "analysis_run": analysis_run,
            "worker_result": result,
            "worker_meta": {
                key: worker_response.get(key)
                for key in ["model", "duration_seconds", "raw_response_preview"]
                if key in worker_response
            } | {
                "warnings": sorted(set(guardrail_warnings)),
                "allowed_issue_areas": allowed_areas,
                "analysis_scope": analysis_scope,
                "model_parameters": model_parameters(),
                "image_payload": payload_metadata,
                "worker_received_image_count": worker_response.get("received_image_count"),
                "worker_received_image_labels": worker_response.get("received_image_labels"),
                "worker_received_image_hashes": worker_response.get("received_image_hashes"),
                "worker_received_image_dimensions": worker_response.get("received_image_dimensions"),
            },
            "finding_count": finding_count,
            "images_sent": len(assets),
            "image_labels_sent": image_labels,
            "image_payload": payload_metadata,
            "allowed_issue_areas": allowed_areas,
            "warnings": sorted(set(guardrail_warnings)),
            "analysis_scope": analysis_scope,
        }
    except HTTPException:
        analysis_run.status = "failed"
        analysis_run.error_message = "Remote AI worker request failed."
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        raise
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        raise HTTPException(status_code=502, detail=f"Remote AI grading failed: {exc}") from exc


def choose_single_debug_asset(assets: list[AnalysisAsset], preferred_label: str | None = None) -> AnalysisAsset:
    if preferred_label:
        selected = next((asset for asset in assets if asset.label == preferred_label), None)
        if selected is not None:
            return selected
    return next((asset for asset in assets if asset.label == "front_resized"), assets[0])


def local_ai_debug_single_image(session: Session, owned_card_id: int, image_label: str | None = None) -> dict[str, Any]:
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
    asset = choose_single_debug_asset(assets, image_label)
    debug_assets = [asset]
    allowed_areas = allowed_areas_for_assets(debug_assets)
    image_labels = selected_asset_labels(debug_assets)
    card = session.get(Card, owned_card.card_id) if owned_card.card_id else None
    payload_metadata = image_payload_metadata(debug_assets, owned_card, card)
    warnings = ["limited_image_set"]
    add_stale_image_payload_warnings(session, owned_card_id, payload_metadata, warnings)
    selected_model_name = effective_local_ai_model_name()

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_ai_debug_single_image",
        status="running",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=selected_model_name,
        prompt_version="local_vision_debug_v1",
        analysis_version="local_ai_debug_single_image_v1",
        image_labels_json=json.dumps(image_labels, ensure_ascii=True),
        allowed_areas_json=json.dumps(allowed_areas, ensure_ascii=True),
        warnings_json=json.dumps(warnings, ensure_ascii=True),
        model_parameters_json=json.dumps({**model_parameters(), "model_name": selected_model_name}, ensure_ascii=True),
        analysis_scope="partial",
        image_payload_json=json.dumps(payload_metadata, ensure_ascii=True, default=str),
        recommendation="partial_analysis",
        recommendation_reason="Részleges elemzés, nem teljes grading.",
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    prompt = (
        'Return JSON only: {"ok": true, "summary": "string"}. '
        "This is a partial single-image debug check, not full grading. "
        f"Allowed issue areas: {json.dumps(allowed_areas, ensure_ascii=False)}. "
        "Do not report defects outside those areas."
    )
    if LOCAL_AI_DISABLE_THINKING:
        prompt = (
            "Do not think step by step. Do not output reasoning. Return only JSON. Start with { and end with }.\n"
            f"{prompt}\n/no_think"
        )
    payload = {
        "model": selected_model_name,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, data_url_for_asset(asset)]}],
        "temperature": LOCAL_AI_TEMPERATURE,
        "max_tokens": LOCAL_AI_MAX_TOKENS,
        "response_format": LOCAL_AI_RESPONSE_FORMAT,
        "stream": LOCAL_AI_STREAMING_ENABLED,
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
            "model": selected_model_name,
            "image_label_sent": asset.label,
            "image_payload": payload_metadata,
            "allowed_issue_areas": allowed_areas,
            "warnings": warnings,
            "analysis_scope": "partial",
            "model_parameters": {**model_parameters(), "model_name": selected_model_name},
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
            "model": selected_model_name,
            "image_label_sent": asset.label,
            "image_payload": payload_metadata,
            "allowed_issue_areas": allowed_areas,
            "warnings": warnings,
            "analysis_scope": "partial",
            "model_parameters": {**model_parameters(), "model_name": selected_model_name},
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
    allowed_areas = allowed_areas_for_assets(assets)
    image_labels = selected_asset_labels(assets)
    analysis_scope = analysis_scope_for_assets(assets, pass_type)
    payload_metadata = image_payload_metadata(assets, owned_card, card)
    guardrail_warnings: list[str] = []
    if analysis_scope == "partial":
        add_warning(guardrail_warnings, "limited_image_set")
    add_stale_image_payload_warnings(session, owned_card_id, payload_metadata, guardrail_warnings)
    selected_model_name = effective_local_ai_model_name()

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode=f"local_ai_{pass_type}",
        status="running",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=selected_model_name,
        prompt_version=LOCAL_AI_PROMPT_VERSION,
        analysis_version=f"local_ai_{pass_type}_v1",
        image_labels_json=json.dumps(image_labels, ensure_ascii=True),
        allowed_areas_json=json.dumps(allowed_areas, ensure_ascii=True),
        warnings_json=json.dumps(guardrail_warnings, ensure_ascii=True),
        model_parameters_json=json.dumps({**model_parameters(), "model_name": selected_model_name}, ensure_ascii=True),
        analysis_scope=analysis_scope,
        image_payload_json=json.dumps(payload_metadata, ensure_ascii=True, default=str),
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    raw_response = ""
    parsed_data: dict[str, Any] | None = None
    try:
        raw_response, full_response, parsed_from_reasoning_content = call_openai_compatible(
            build_prompt(
                card,
                opencv_measurements(session, opencv_run),
                pass_type,
                allowed_areas,
                image_labels,
                analysis_scope,
            ),
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
        data = apply_grading_guardrails(data, assets, allowed_areas, analysis_scope, guardrail_warnings)
        parsed_data = data
        save_debug_artifacts(session, analysis_run.id, full_response, parsed_data)
        save_findings(session, analysis_run, data, pass_type if pass_type in {"front", "back"} else "unknown")
        analysis_run.status = "completed"
        analysis_run.human_summary = data.get("overall_visual_condition")
        analysis_run.confidence_level = data.get("confidence_level", "low")
        analysis_run.recommendation = "partial_analysis" if analysis_scope == "partial" else "local_ai_findings_completed"
        analysis_run.recommendation_reason = (
            "Részleges elemzés, nem teljes grading."
            if analysis_scope == "partial"
            else analysis_run.recommendation_reason
        )
        set_analysis_debug_metadata(analysis_run, assets, allowed_areas, guardrail_warnings, analysis_scope, payload_metadata)
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
        if analysis_scope == "partial":
            session.refresh(analysis_run)
        else:
            analysis_run = score_analysis_run(session, analysis_run.id)
        return {
            "analysis_run": analysis_run,
            "finding_count": len(findings),
            "images_sent": len(assets),
            "image_labels_sent": image_labels,
            "image_payload": payload_metadata,
            "allowed_issue_areas": allowed_areas,
            "warnings": sorted(set(guardrail_warnings)),
            "analysis_scope": analysis_scope,
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
    selected_model_name = effective_local_ai_model_name()
    aggregate_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_ai_aggregate",
        status="completed",
        model_provider=LOCAL_AI_PROVIDER,
        model_name=selected_model_name,
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
