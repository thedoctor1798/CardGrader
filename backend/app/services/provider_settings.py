import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from .. import config
from ..models import PriceProviderSetting
from ..models.core import utc_now


ONLINE_PROVIDERS = {"poketrace", "tcgdex", "pokemontcg"}
SECRET_FIELDS = {"api_key"}
PROVIDERS = ("manual", "local_json", "poketrace", "tcgdex", "pokemontcg")


@dataclass
class EffectiveProviderConfig:
    provider: str
    enabled: bool
    configured: bool
    source: str
    config: dict[str, Any]
    secrets: dict[str, Any]
    missing: list[str]
    secret_encrypted: bool = False


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("-", "")
    aliases = {
        "pokemon_tcg": "pokemontcg",
        "pokemon-tcg": "pokemontcg",
        "pokemon tcg": "pokemontcg",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in PROVIDERS:
        raise HTTPException(status_code=404, detail={"error": "provider_not_found", "message": "Unknown price provider."})
    return normalized


def provider_setting(session: Session, provider: str) -> PriceProviderSetting | None:
    normalized = normalize_provider(provider)
    return session.exec(select(PriceProviderSetting).where(PriceProviderSetting.provider == normalized)).first()


def list_safe_provider_settings(session: Session) -> list[dict[str, Any]]:
    return [safe_provider_status(session, provider) for provider in PROVIDERS]


def safe_provider_status(session: Session, provider: str) -> dict[str, Any]:
    effective = effective_provider_config(session, provider)
    payload = {
        "provider": effective.provider,
        "enabled": effective.enabled,
        "configured": effective.configured,
        "source": effective.source,
        "missing": effective.missing,
        "secret_encrypted": effective.secret_encrypted,
    }
    payload.update(safe_config_fields(effective.provider, effective.config))
    if "api_key" in effective.secrets:
        payload["masked_api_key"] = mask_secret(str(effective.secrets["api_key"]))
    elif effective.provider in {"poketrace", "pokemontcg"}:
        payload["masked_api_key"] = None
    return payload


def safe_config_fields(provider: str, provider_config: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "poketrace": (
            "plan",
            "market",
            "base_url",
            "daily_limit",
            "burst_limit",
            "burst_window_seconds",
            "timeout_seconds",
            "cache_ttl_hours",
            "min_match_score",
            "fetch_history",
            "history_period",
            "respect_retry_after",
            "expected_sources",
        ),
        "tcgdex": ("base_url", "timeout_seconds", "rate_limit_seconds", "min_match_score"),
        "pokemontcg": ("base_url", "timeout_seconds", "rate_limit_seconds", "min_match_score"),
        "local_json": ("path_info",),
        "manual": (),
    }
    return {key: provider_config.get(key) for key in allowed.get(provider, ()) if key in provider_config}


def effective_provider_config(session: Session | None, provider: str) -> EffectiveProviderConfig:
    normalized = normalize_provider(provider)
    setting = provider_setting(session, normalized) if session is not None else None
    env_config = env_provider_config(normalized)
    env_secrets = env_provider_secrets(normalized)
    config_source = "default"
    provider_config = dict(env_config)
    secrets = dict(env_secrets)
    enabled = bool(provider_config.get("enabled", False))
    secret_encrypted = False

    if setting is not None:
        config_source = "database"
        stored_config = parse_json_dict(setting.config_json)
        provider_config.update(stored_config)
        stored_secrets = decrypt_setting_secrets(setting)
        if "__error" not in stored_secrets:
            secrets.update(stored_secrets)
        enabled = setting.enabled
        secret_encrypted = setting.secret_encrypted
    elif env_has_provider_values(normalized):
        config_source = "env"

    provider_config = apply_provider_defaults(normalized, provider_config)
    provider_config["enabled"] = enabled
    configured, missing = provider_configured(normalized, enabled, secrets)
    return EffectiveProviderConfig(
        provider=normalized,
        enabled=enabled,
        configured=configured,
        source=config_source,
        config=provider_config,
        secrets=secrets,
        missing=missing,
        secret_encrypted=secret_encrypted,
    )


def env_provider_config(provider: str) -> dict[str, Any]:
    if provider == "manual":
        return {"enabled": True}
    if provider == "local_json":
        return {"enabled": "local_json" in config.PRICE_SOURCES, "path_info": "/app/catalog/prices or /app/data/prices"}
    if provider == "poketrace":
        return {
            "enabled": config.POKETRACE_ENABLED,
            "base_url": config.POKETRACE_BASE_URL,
            "market": config.POKETRACE_MARKET,
            "timeout_seconds": config.POKETRACE_TIMEOUT_SECONDS,
            "cache_ttl_hours": config.POKETRACE_CACHE_TTL_HOURS,
            "min_match_score": config.POKETRACE_MIN_MATCH_SCORE,
            "fetch_history": config.POKETRACE_FETCH_HISTORY,
            "history_period": config.POKETRACE_HISTORY_PERIOD,
            "plan": config.POKETRACE_PLAN,
            "daily_limit": config.POKETRACE_DAILY_LIMIT,
            "burst_limit": config.POKETRACE_BURST_LIMIT,
            "burst_window_seconds": config.POKETRACE_BURST_WINDOW_SECONDS,
            "respect_retry_after": config.POKETRACE_RESPECT_RETRY_AFTER,
        }
    if provider == "tcgdex":
        return {
            "enabled": config.TCGDEX_ENABLED,
            "base_url": config.TCGDEX_BASE_URL,
            "timeout_seconds": config.TCGDEX_TIMEOUT_SECONDS,
            "rate_limit_seconds": config.TCGDEX_RATE_LIMIT_SECONDS,
            "min_match_score": config.TCGDEX_MIN_MATCH_SCORE,
        }
    if provider == "pokemontcg":
        return {
            "enabled": config.POKEMONTCG_ENABLED,
            "base_url": config.POKEMONTCG_BASE_URL,
            "timeout_seconds": config.POKEMONTCG_TIMEOUT_SECONDS,
            "rate_limit_seconds": config.POKEMONTCG_RATE_LIMIT_SECONDS,
            "min_match_score": config.POKEMONTCG_MIN_MATCH_SCORE,
        }
    return {"enabled": False}


def env_provider_secrets(provider: str) -> dict[str, Any]:
    if provider == "poketrace" and config.POKETRACE_API_KEY:
        return {"api_key": config.POKETRACE_API_KEY}
    if provider == "pokemontcg" and config.POKEMONTCG_API_KEY:
        return {"api_key": config.POKEMONTCG_API_KEY}
    return {}


def env_has_provider_values(provider: str) -> bool:
    prefixes = {
        "poketrace": "POKETRACE_",
        "tcgdex": "TCGDEX_",
        "pokemontcg": "POKEMONTCG_",
    }
    prefix = prefixes.get(provider)
    return bool(prefix and any(key.startswith(prefix) for key in os.environ))


def apply_provider_defaults(provider: str, provider_config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(provider_config)
    if provider == "poketrace":
        plan = str(merged.get("plan") or "free").lower()
        if plan not in config.POKETRACE_PLAN_PRESETS:
            plan = "free"
        preset = config.POKETRACE_PLAN_PRESETS[plan]
        merged["plan"] = plan
        merged["daily_limit"] = int_or_default(merged.get("daily_limit"), int(preset["daily_limit"]))
        merged["burst_limit"] = int_or_default(merged.get("burst_limit"), int(preset["burst_limit"]))
        merged["burst_window_seconds"] = int_or_default(
            merged.get("burst_window_seconds"),
            int(preset["burst_window_seconds"]),
        )
        merged["expected_sources"] = list(preset["expected_sources"])
        merged["market"] = str(merged.get("market") or "US").upper()
        merged["base_url"] = str(merged.get("base_url") or "https://api.poketrace.com/v1").rstrip("/")
        merged["timeout_seconds"] = int_or_default(merged.get("timeout_seconds"), 30)
        merged["cache_ttl_hours"] = int_or_default(merged.get("cache_ttl_hours"), config.PRICE_PROVIDER_CACHE_TTL_HOURS)
        merged["min_match_score"] = int_or_default(merged.get("min_match_score"), config.PRICE_PROVIDER_MIN_MATCH_SCORE)
        merged["respect_retry_after"] = bool_or_default(merged.get("respect_retry_after"), True)
    elif provider == "tcgdex":
        merged["base_url"] = str(merged.get("base_url") or "https://api.tcgdex.net/v2").rstrip("/")
        merged["timeout_seconds"] = int_or_default(merged.get("timeout_seconds"), 30)
        merged["rate_limit_seconds"] = float_or_default(merged.get("rate_limit_seconds"), 2.0)
        merged["min_match_score"] = int_or_default(merged.get("min_match_score"), config.PRICE_PROVIDER_MIN_MATCH_SCORE)
    elif provider == "pokemontcg":
        merged["base_url"] = str(merged.get("base_url") or "https://api.pokemontcg.io/v2").rstrip("/")
        merged["timeout_seconds"] = int_or_default(merged.get("timeout_seconds"), 30)
        merged["rate_limit_seconds"] = float_or_default(merged.get("rate_limit_seconds"), 2.0)
        merged["min_match_score"] = int_or_default(merged.get("min_match_score"), config.PRICE_PROVIDER_MIN_MATCH_SCORE)
    return merged


def provider_configured(provider: str, enabled: bool, secrets: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if provider in {"manual", "local_json", "tcgdex"}:
        return enabled, missing
    if provider == "poketrace" and not secrets.get("api_key"):
        missing.append("POKETRACE_API_KEY")
    if provider == "pokemontcg":
        return enabled, missing
    return enabled and not missing, missing


def save_provider_setting(session: Session, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_provider(provider)
    existing = provider_setting(session, normalized)
    enabled = bool(payload.get("enabled", existing.enabled if existing else False))
    clear_secret = bool(payload.get("clear_secret", False))
    new_secret_values = {
        key: value.strip()
        for key, value in payload.items()
        if key in SECRET_FIELDS and isinstance(value, str) and value.strip()
    }
    config_payload = {
        key: value
        for key, value in payload.items()
        if key not in SECRET_FIELDS and key not in {"clear_secret", "provider"} and value is not None
    }

    secret_json = existing.secret_json if existing else None
    secret_encrypted = existing.secret_encrypted if existing else False
    if clear_secret:
        secret_json = None
        secret_encrypted = False
    elif new_secret_values:
        secret_json, secret_encrypted = encode_secret_json(new_secret_values)

    setting = existing or PriceProviderSetting(provider=normalized)
    setting.enabled = enabled
    if config_payload:
        setting.config_json = json.dumps(config_payload, ensure_ascii=True, default=str)
    elif existing is None:
        setting.config_json = None
    setting.secret_json = secret_json
    setting.secret_encrypted = secret_encrypted
    setting.updated_at = utc_now()
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return safe_provider_status(session, normalized)


def encode_secret_json(secrets: dict[str, Any]) -> tuple[str, bool]:
    if config.CONFIG_ENCRYPTION_KEY:
        return encrypt_json(secrets, config.CONFIG_ENCRYPTION_KEY), True
    if not config.ALLOW_UNENCRYPTED_PROVIDER_SECRETS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "provider_secret_storage_not_configured",
                "message": "Set CONFIG_ENCRYPTION_KEY or ALLOW_UNENCRYPTED_PROVIDER_SECRETS=true before saving provider API keys.",
            },
        )
    return json.dumps(secrets, ensure_ascii=True), False


def decrypt_setting_secrets(setting: PriceProviderSetting | None) -> dict[str, Any]:
    if setting is None or not setting.secret_json:
        return {}
    try:
        if setting.secret_encrypted:
            if not config.CONFIG_ENCRYPTION_KEY:
                return {"__error": "provider_secret_decryption_key_missing"}
            return decrypt_json(setting.secret_json, config.CONFIG_ENCRYPTION_KEY)
        return parse_json_dict(setting.secret_json)
    except (ValueError, json.JSONDecodeError):
        return {"__error": "provider_secret_decryption_failed"}


def encrypt_json(payload: dict[str, Any], key: str) -> str:
    plaintext = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    nonce = os.urandom(16)
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    ciphertext = xor_bytes(plaintext, key_bytes, nonce)
    digest = hmac.new(key_bytes, nonce + ciphertext, hashlib.sha256).digest()
    return json.dumps(
        {
            "v": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "hmac": base64.b64encode(digest).decode("ascii"),
        },
        ensure_ascii=True,
    )


def decrypt_json(envelope_json: str, key: str) -> dict[str, Any]:
    envelope = json.loads(envelope_json)
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    expected_hmac = base64.b64decode(envelope["hmac"])
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    digest = hmac.new(key_bytes, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(digest, expected_hmac):
        raise ValueError("secret hmac mismatch")
    plaintext = xor_bytes(ciphertext, key_bytes, nonce)
    return parse_json_dict(plaintext.decode("utf-8"))


def xor_bytes(data: bytes, key_bytes: bytes, nonce: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(data):
        block = hashlib.sha256(key_bytes + nonce + counter.to_bytes(4, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(value ^ output[index] for index, value in enumerate(data))


def parse_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    suffix = secret[-4:] if len(secret) >= 4 else secret
    prefix = ""
    if "_" in secret[:6]:
        prefix = secret.split("_", 1)[0] + "_"
    return f"{prefix}****{suffix}"


def int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_or_default(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}
