from ..config import CATALOG_DIR, DATA_DIR, LOG_DIR, MEDIA_DIR


def ensure_app_dirs():
    for path in [DATA_DIR, MEDIA_DIR, CATALOG_DIR, LOG_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    ensure_media_dirs()


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
