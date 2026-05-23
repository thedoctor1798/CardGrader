from pathlib import Path
import os

# workspace root (E:/CardGrader)
ROOT = Path(__file__).resolve().parents[2]

HOST = "127.0.0.1"
PORT = 8710

DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"

LOCAL_AI_ENABLED = os.getenv("LOCAL_AI_ENABLED", "false").lower() == "true"
LOCAL_AI_PROVIDER = os.getenv("LOCAL_AI_PROVIDER", "lmstudio")
LOCAL_AI_BASE_URL = os.getenv("LOCAL_AI_BASE_URL", "http://127.0.0.1:1234/v1")
LOCAL_AI_MODEL_NAME = os.getenv("LOCAL_AI_MODEL_NAME", "")
LOCAL_AI_TIMEOUT_SECONDS = int(os.getenv("LOCAL_AI_TIMEOUT_SECONDS", "120"))
