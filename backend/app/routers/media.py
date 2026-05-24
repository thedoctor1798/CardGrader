from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select

from ..config import MEDIA_DIR, ROOT
from ..database import get_session
from ..models import CardMedia, OwnedCard
from ..schemas import CardMediaRead

router = APIRouter()

ALLOWED_LABELS = {
    "front",
    "back",
    "corner_tl",
    "corner_tr",
    "corner_bl",
    "corner_br",
    "edge_top",
    "edge_right",
    "edge_bottom",
    "edge_left",
    "video",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MAX_FILE_SIZE_BYTES = 30 * 1024 * 1024


def infer_media_type(extension: str) -> str:
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Allowed extensions: .jpg, .jpeg, .png, .webp, .mp4, .mov, .webm",
    )


def validate_media_type(extension: str, media_type: Optional[str]) -> str:
    inferred = infer_media_type(extension)
    if media_type is None:
        return inferred

    normalized = media_type.strip().lower()
    if normalized not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="media_type must be image or video")
    if normalized != inferred:
        raise HTTPException(
            status_code=400,
            detail=f"media_type {normalized} does not match file extension {extension}",
        )
    return normalized


def relative_to_root(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def media_file_from_url_path(path: str) -> Path:
    requested = (MEDIA_DIR / path).resolve()
    media_root = MEDIA_DIR.resolve()
    if requested != media_root and media_root not in requested.parents:
        raise HTTPException(status_code=400, detail="Invalid media path")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return requested


async def save_upload(file: UploadFile, destination: Path) -> int:
    total_size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("wb") as out_file:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE_BYTES:
                out_file.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="File exceeds 30 MB limit")
            out_file.write(chunk)

    return total_size


def read_image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded image could not be opened") from exc


@router.post("/api/owned-cards/{owned_card_id}/media", response_model=CardMediaRead, status_code=201)
async def upload_owned_card_media(
    owned_card_id: int,
    file: UploadFile = File(...),
    label: str = Form(...),
    media_type: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
):
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    normalized_label = label.strip().lower()
    if normalized_label not in ALLOWED_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported media label")

    original_filename = Path(file.filename or "").name
    extension = Path(original_filename).suffix.lower()
    normalized_media_type = validate_media_type(extension, media_type)
    filename = f"{normalized_label}_{uuid4().hex}{extension}"
    destination = MEDIA_DIR / "originals" / str(owned_card_id) / filename

    file_size = await save_upload(file, destination)
    width = None
    height = None
    if normalized_media_type == "image":
        width, height = read_image_size(destination)

    media = CardMedia(
        owned_card_id=owned_card_id,
        media_type=normalized_media_type,
        label=normalized_label,
        file_path=relative_to_root(destination),
        original_filename=original_filename,
        width=width,
        height=height,
        file_size_bytes=file_size,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


@router.get("/api/owned-cards/{owned_card_id}/media", response_model=List[CardMediaRead])
def list_owned_card_media(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    statement = (
        select(CardMedia)
        .where(CardMedia.owned_card_id == owned_card_id)
        .order_by(CardMedia.created_at.desc(), CardMedia.id.desc())
    )
    return session.exec(statement).all()


@router.delete("/api/media/{media_id}", status_code=204)
def delete_media(media_id: int, session: Session = Depends(get_session)):
    media = session.get(CardMedia, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    file_path = (ROOT / media.file_path).resolve()
    media_root = MEDIA_DIR.resolve()
    if file_path == media_root or media_root in file_path.parents:
        file_path.unlink(missing_ok=True)

    session.delete(media)
    session.commit()


@router.get("/media/{path:path}")
def serve_media(path: str):
    return FileResponse(media_file_from_url_path(path))
