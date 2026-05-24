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

HOST = "127.0.0.1"
PORT = 8710

DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"


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


def get_clamped_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, get_int_env(name, default)))


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
LOCAL_AI_MODEL_NAME = os.getenv("LOCAL_AI_MODEL_NAME", "")
LOCAL_AI_TIMEOUT_SECONDS = get_int_env("LOCAL_AI_TIMEOUT_SECONDS", 120)
LOCAL_AI_MAX_IMAGES = get_clamped_int_env("LOCAL_AI_MAX_IMAGES", 1, 1, 10)
LOCAL_AI_MAX_TOKENS = get_clamped_int_env("LOCAL_AI_MAX_TOKENS", 4096, 300, 8192)
LOCAL_AI_DISABLE_THINKING = get_bool_env("LOCAL_AI_DISABLE_THINKING", True)
