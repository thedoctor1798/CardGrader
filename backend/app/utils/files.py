from pathlib import Path
from ..config import MEDIA_DIR


def ensure_media_dirs():
    subfolders = [
        "originals",
        "resized",
        "derived",
        "normalized",
        "crops",
        "annotated",
        "video_frames",
        "reports",
    ]
    for sf in subfolders:
        p = MEDIA_DIR / sf
        p.mkdir(parents=True, exist_ok=True)
