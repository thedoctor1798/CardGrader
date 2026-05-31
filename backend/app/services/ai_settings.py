import json
from typing import Any

from sqlmodel import Session, select

from ..config import (
    AI_PHASE_A_MAX_OUTPUT_TOKENS,
    AI_PHASE_B_MAX_OUTPUT_TOKENS,
    LOCAL_AI_DISABLE_THINKING,
    LOCAL_AI_MODEL_NAME,
    SEND_DIAGNOSTIC_IMAGES_TO_AI,
)
from ..models import AppSetting
from .local_ai import LOCAL_AI_TEMPERATURE

AI_SETTINGS_KEY = "local_ai_settings"

DEFAULT_AI_SETTINGS: dict[str, Any] = {
    "ai_model": LOCAL_AI_MODEL_NAME or "auto",
    "context_tokens": 15000,
    "phase_a_tokens": AI_PHASE_A_MAX_OUTPUT_TOKENS or 1500,
    "phase_b_tokens": AI_PHASE_B_MAX_OUTPUT_TOKENS or 2500,
    "temperature": LOCAL_AI_TEMPERATURE,
    "send_diagnostic_images": SEND_DIAGNOSTIC_IMAGES_TO_AI,
    "disable_thinking": LOCAL_AI_DISABLE_THINKING,
}


def _coerce_settings(raw: dict[str, Any]) -> dict[str, Any]:
    settings = {**DEFAULT_AI_SETTINGS, **raw}
    settings["ai_model"] = str(settings.get("ai_model") or "auto").strip() or "auto"
    settings["context_tokens"] = max(1000, min(200000, int(settings.get("context_tokens") or 15000)))
    settings["phase_a_tokens"] = max(300, min(20000, int(settings.get("phase_a_tokens") or 1500)))
    settings["phase_b_tokens"] = max(300, min(20000, int(settings.get("phase_b_tokens") or 2500)))
    settings["temperature"] = max(0.0, min(2.0, float(settings.get("temperature") or 0.0)))
    settings["send_diagnostic_images"] = bool(settings.get("send_diagnostic_images"))
    settings["disable_thinking"] = bool(settings.get("disable_thinking"))
    return settings


def get_ai_settings(session: Session) -> dict[str, Any]:
    row = session.exec(select(AppSetting).where(AppSetting.key == AI_SETTINGS_KEY)).first()
    if row is None or not row.value_json:
        return _coerce_settings({})
    try:
        parsed = json.loads(row.value_json)
    except json.JSONDecodeError:
        parsed = {}
    return _coerce_settings(parsed if isinstance(parsed, dict) else {})


def update_ai_settings(session: Session, updates: dict[str, Any]) -> dict[str, Any]:
    current = get_ai_settings(session)
    next_settings = _coerce_settings({**current, **updates})
    row = session.exec(select(AppSetting).where(AppSetting.key == AI_SETTINGS_KEY)).first()
    if row is None:
        row = AppSetting(key=AI_SETTINGS_KEY)
    row.value_json = json.dumps(next_settings, ensure_ascii=True)
    session.add(row)
    session.commit()
    session.refresh(row)
    return next_settings
