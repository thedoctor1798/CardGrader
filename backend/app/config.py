from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# workspace root: E:/CardGrader
ROOT = Path(__file__).resolve().parents[2]

# backend root: E:/CardGrader/backend
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Load backend/.env and optional project root .env before reading os.getenv values.
# This keeps config local-only and avoids requiring system-wide env vars.
if load_dotenv is not None:
    load_dotenv(BACKEND_DIR / ".env", override=False)
    load_dotenv(ROOT / ".env", override=False)

def get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}


def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def get_optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def get_clamped_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, get_int_env(name, default)))


def get_path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8711",
    "http://127.0.0.1:8711",
]


def get_csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


APP_MODE = os.getenv("APP_MODE", "local").strip().lower() or "local"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = get_int_env("PORT", 8710)
DATA_DIR = get_path_env("DATA_DIR", ROOT / "data")
MEDIA_DIR = get_path_env("MEDIA_DIR", ROOT / "media")
CATALOG_DIR = get_path_env("CATALOG_DIR", ROOT / "catalog")
LOG_DIR = get_path_env("LOG_DIR", ROOT / "logs")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'cardgrader.db').as_posix()}")
CORS_ORIGINS = get_csv_env("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
PRICE_FETCH_ENABLED = get_bool_env("PRICE_FETCH_ENABLED", True)
PRICE_REFRESH_ENABLED = get_bool_env("PRICE_REFRESH_ENABLED", False)
PRICE_REFRESH_INTERVAL_HOURS = get_int_env("PRICE_REFRESH_INTERVAL_HOURS", 24)
PRICE_DEFAULT_CURRENCY = (os.getenv("PRICE_DEFAULT_CURRENCY", "HUF").strip().upper() or "HUF")
PRICE_RATE_LIMIT_SECONDS = get_float_env("PRICE_RATE_LIMIT_SECONDS", 3.0)
PRICE_REQUEST_TIMEOUT_SECONDS = get_int_env("PRICE_REQUEST_TIMEOUT_SECONDS", 30)
PRICE_SOURCES = get_csv_env("PRICE_SOURCES", ["manual", "local_json"])
PRICE_FETCH_AFTER_RECOGNITION = get_bool_env("PRICE_FETCH_AFTER_RECOGNITION", False)
PRICE_FX_EUR_HUF = get_optional_float_env("PRICE_FX_EUR_HUF")
PRICE_FX_USD_HUF = get_optional_float_env("PRICE_FX_USD_HUF")
PRICE_PROVIDER_CACHE_TTL_HOURS = get_int_env("PRICE_PROVIDER_CACHE_TTL_HOURS", 24)
PRICE_EXTERNAL_FETCH_ENABLED = get_bool_env("PRICE_EXTERNAL_FETCH_ENABLED", True)
PRICE_PROVIDER_MIN_MATCH_SCORE = get_int_env("PRICE_PROVIDER_MIN_MATCH_SCORE", 70)
FX_CONVERSION_ENABLED = get_bool_env("FX_CONVERSION_ENABLED", True)
FX_DEFAULT_TARGET_CURRENCY = os.getenv("FX_DEFAULT_TARGET_CURRENCY", "HUF").strip().upper() or "HUF"
FX_PROVIDER = os.getenv("FX_PROVIDER", "frankfurter").strip().lower() or "frankfurter"
FX_PROVIDER_BASE_URL = os.getenv("FX_PROVIDER_BASE_URL", "https://api.frankfurter.dev/v2").rstrip("/")
FX_PROVIDER_FALLBACK_BASE_URL = os.getenv("FX_PROVIDER_FALLBACK_BASE_URL", "https://api.frankfurter.dev/v1").rstrip("/")
FX_USER_AGENT = os.getenv("FX_USER_AGENT", "CardGrader/1.0").strip() or "CardGrader/1.0"
FX_CACHE_TTL_HOURS = get_int_env("FX_CACHE_TTL_HOURS", 12)
FX_TIMEOUT_SECONDS = get_int_env("FX_TIMEOUT_SECONDS", 15)
FX_FALLBACK_TO_STATIC_RATES = get_bool_env("FX_FALLBACK_TO_STATIC_RATES", True)

CONFIG_ENCRYPTION_KEY = os.getenv("CONFIG_ENCRYPTION_KEY", "")
ALLOW_UNENCRYPTED_PROVIDER_SECRETS = get_bool_env("ALLOW_UNENCRYPTED_PROVIDER_SECRETS", False)

POKETRACE_PLAN_PRESETS = {
    "free": {
        "daily_limit": 250,
        "burst_limit": 1,
        "burst_window_seconds": 2,
        "expected_sources": ["eBay", "TCGPlayer"],
    },
    "pro": {
        "daily_limit": 10000,
        "burst_limit": 30,
        "burst_window_seconds": 10,
        "expected_sources": ["eBay", "TCGPlayer", "Cardmarket"],
    },
    "scale": {
        "daily_limit": 100000,
        "burst_limit": 60,
        "burst_window_seconds": 10,
        "expected_sources": ["eBay", "TCGPlayer", "Cardmarket"],
    },
}


def get_poketrace_plan() -> str:
    plan = os.getenv("POKETRACE_PLAN", "free").strip().lower() or "free"
    return plan if plan in POKETRACE_PLAN_PRESETS else "free"


def get_poketrace_plan_int(name: str, key: str) -> int:
    plan = get_poketrace_plan()
    explicit = get_optional_int_env(name)
    if explicit is not None:
        return explicit
    return int(POKETRACE_PLAN_PRESETS[plan][key])


POKETRACE_ENABLED = get_bool_env("POKETRACE_ENABLED", False)
POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY", "")
POKETRACE_BASE_URL = os.getenv("POKETRACE_BASE_URL", "https://api.poketrace.com/v1").rstrip("/")
POKETRACE_MARKET = (os.getenv("POKETRACE_MARKET", "US").strip().upper() or "US")
POKETRACE_TIMEOUT_SECONDS = get_int_env("POKETRACE_TIMEOUT_SECONDS", 30)
POKETRACE_CACHE_TTL_HOURS = get_int_env("POKETRACE_CACHE_TTL_HOURS", PRICE_PROVIDER_CACHE_TTL_HOURS)
POKETRACE_MIN_MATCH_SCORE = get_int_env("POKETRACE_MIN_MATCH_SCORE", PRICE_PROVIDER_MIN_MATCH_SCORE)
POKETRACE_FETCH_HISTORY = get_bool_env("POKETRACE_FETCH_HISTORY", False)
POKETRACE_HISTORY_PERIOD = os.getenv("POKETRACE_HISTORY_PERIOD", "30d")
POKETRACE_PLAN = get_poketrace_plan()
POKETRACE_DAILY_LIMIT = get_poketrace_plan_int("POKETRACE_DAILY_LIMIT", "daily_limit")
POKETRACE_BURST_LIMIT = get_poketrace_plan_int("POKETRACE_BURST_LIMIT", "burst_limit")
POKETRACE_BURST_WINDOW_SECONDS = get_poketrace_plan_int("POKETRACE_BURST_WINDOW_SECONDS", "burst_window_seconds")
POKETRACE_RESPECT_RETRY_AFTER = get_bool_env("POKETRACE_RESPECT_RETRY_AFTER", True)

TCGDEX_ENABLED = get_bool_env("TCGDEX_ENABLED", False)
TCGDEX_BASE_URL = os.getenv("TCGDEX_BASE_URL", "https://api.tcgdex.net/v2").rstrip("/")
TCGDEX_TIMEOUT_SECONDS = get_int_env("TCGDEX_TIMEOUT_SECONDS", 30)
TCGDEX_RATE_LIMIT_SECONDS = get_float_env("TCGDEX_RATE_LIMIT_SECONDS", 2.0)
TCGDEX_MIN_MATCH_SCORE = get_int_env("TCGDEX_MIN_MATCH_SCORE", PRICE_PROVIDER_MIN_MATCH_SCORE)

POKEMONTCG_ENABLED = get_bool_env("POKEMONTCG_ENABLED", False)
POKEMONTCG_API_KEY = os.getenv("POKEMONTCG_API_KEY", "")
POKEMONTCG_BASE_URL = os.getenv("POKEMONTCG_BASE_URL", "https://api.pokemontcg.io/v2").rstrip("/")
POKEMONTCG_TIMEOUT_SECONDS = get_int_env("POKEMONTCG_TIMEOUT_SECONDS", 30)
POKEMONTCG_RATE_LIMIT_SECONDS = get_float_env("POKEMONTCG_RATE_LIMIT_SECONDS", 2.0)
POKEMONTCG_MIN_MATCH_SCORE = get_int_env("POKEMONTCG_MIN_MATCH_SCORE", PRICE_PROVIDER_MIN_MATCH_SCORE)


LOCAL_AI_MODES = {"disabled", "server_local", "remote_worker"}
_LEGACY_LOCAL_AI_ENABLED = get_bool_env("LOCAL_AI_ENABLED", False)
_LOCAL_AI_MODE = os.getenv("LOCAL_AI_MODE", "").strip().lower()
if not _LOCAL_AI_MODE:
    _LOCAL_AI_MODE = "server_local" if _LEGACY_LOCAL_AI_ENABLED else "disabled"
if _LOCAL_AI_MODE not in LOCAL_AI_MODES:
    _LOCAL_AI_MODE = "server_local" if _LEGACY_LOCAL_AI_ENABLED else "disabled"
LOCAL_AI_MODE = _LOCAL_AI_MODE
LOCAL_AI_ENABLED = LOCAL_AI_MODE != "disabled"
LOCAL_AI_PROVIDER = os.getenv("LOCAL_AI_PROVIDER", "lmstudio")
LOCAL_AI_BASE_URL = os.getenv("LOCAL_AI_BASE_URL", "http://127.0.0.1:1234/v1")
LOCAL_AI_WORKER_BASE_URL = os.getenv("LOCAL_AI_WORKER_BASE_URL", "")
AI_WORKER_SHARED_TOKEN = os.getenv("AI_WORKER_SHARED_TOKEN", "")
LOCAL_AI_MODEL_NAME = os.getenv("LOCAL_AI_MODEL_NAME", "")
LOCAL_AI_TIMEOUT_SECONDS = get_int_env("LOCAL_AI_TIMEOUT_SECONDS", 120)
LOCAL_AI_MAX_IMAGES = get_clamped_int_env("LOCAL_AI_MAX_IMAGES", 1, 1, 10)
LOCAL_AI_MAX_TOKENS = get_clamped_int_env("LOCAL_AI_MAX_TOKENS", 4096, 300, 8192)
LOCAL_AI_DISABLE_THINKING = get_bool_env("LOCAL_AI_DISABLE_THINKING", True)
CARD_RECOGNITION_TOP_K = get_clamped_int_env("CARD_RECOGNITION_TOP_K", 10, 1, 25)
CARD_RECOGNITION_MIN_SCORE = get_clamped_int_env("CARD_RECOGNITION_MIN_SCORE", 30, 0, 100)
