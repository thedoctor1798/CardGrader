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
