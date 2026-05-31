import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import or_
from sqlmodel import Session, select

from ..config import (
    ENABLE_CENTERING_DETECTION,
    ENABLE_IMAGE_PREPROCESSING,
    ENABLE_MANUAL_CENTERING_CORRECTION,
    MEDIA_DIR,
    ROOT,
)
from ..models import CardMedia, OwnedCard, ProcessedCardImage
from .centering import (
    calculate_centering_from_warped_card,
    detect_card_boundary,
    draw_centering_debug,
    fallback_corners,
    order_corners,
    warp_card_to_standard,
)

logger = logging.getLogger(__name__)

PREPROCESSING_VERSION = "phase16_v1"
MAX_NORMALIZED_LONG_EDGE = 1800
JPEG_QUALITY = 92
DIAGNOSTIC_KEYS = [
    "original_normalized",
    "grayscale_clahe",
    "sobel_edges",
    "emboss_surface",
    "highpass_texture",
    "canny_edges",
    "perspective_corrected",
    "centering_debug",
]


def utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def relative_to_root(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def resolve_media_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    media_root = MEDIA_DIR.resolve()
    if path != media_root and media_root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Media file missing: {relative_path}")
    return path


def read_source_image(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError):
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise
        return image


def write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".png":
        success, encoded = cv2.imencode(".png", image)
    else:
        success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not success:
        raise RuntimeError(f"Could not encode image: {path}")
    encoded.tofile(str(path))


def normalize_original(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge <= MAX_NORMALIZED_LONG_EDGE:
        return image.copy()
    scale = MAX_NORMALIZED_LONG_EDGE / long_edge
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def clahe_gray(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)


def sobel_edges(image: np.ndarray) -> np.ndarray:
    gray = clahe_gray(image)
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(sobel_x, sobel_y)
    normalized = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(normalized.astype("uint8"))


def emboss_surface(image: np.ndarray) -> np.ndarray:
    gray = clahe_gray(image)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    kernel = np.array(
        [
            [-3, -2, -1],
            [-2, 1, 2],
            [-1, 2, 3],
        ],
        dtype="float32",
    )
    embossed = cv2.filter2D(blurred, cv2.CV_32F, kernel) + 128.0
    normalized = cv2.normalize(embossed, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.convertScaleAbs(normalized, alpha=1.15, beta=0)


def highpass_texture(image: np.ndarray) -> np.ndarray:
    gray = clahe_gray(image)
    blurred = cv2.GaussianBlur(gray, (17, 17), 0)
    highpass = cv2.addWeighted(gray, 1.6, blurred, -0.6, 128)
    normalized = cv2.normalize(highpass, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(normalized.astype("uint8"))


def canny_edges(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blurred))
    lower = int(max(20, 0.66 * median))
    upper = int(min(220, 1.33 * median))
    edges = cv2.Canny(blurred, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)


def json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def latest_side_media(session: Session, owned_card_id: int, side: str) -> CardMedia | None:
    return session.exec(
        select(CardMedia)
        .where(CardMedia.owned_card_id == owned_card_id)
        .where(CardMedia.media_type == "image")
        .where(or_(CardMedia.label == side, CardMedia.label.like(f"{side}_%")))
        .order_by(CardMedia.created_at.desc(), CardMedia.id.desc())
    ).first()


def latest_processed_side(session: Session, owned_card_id: int, side: str) -> ProcessedCardImage | None:
    return session.exec(
        select(ProcessedCardImage)
        .where(ProcessedCardImage.owned_card_id == owned_card_id)
        .where(ProcessedCardImage.side == side)
        .order_by(ProcessedCardImage.created_at.desc(), ProcessedCardImage.id.desc())
    ).first()


def upsert_processed_side(
    session: Session,
    owned_card_id: int,
    side: str,
    media_id: int | None,
    analysis: dict[str, Any],
    analysis_path: Path,
) -> ProcessedCardImage:
    row = latest_processed_side(session, owned_card_id, side) or ProcessedCardImage(
        owned_card_id=owned_card_id,
        side=side,
    )
    row.media_id = media_id
    row.preprocessing_version = PREPROCESSING_VERSION
    row.status = analysis.get("status", "completed")
    row.generated_images_json = json.dumps(analysis.get("generated_images", {}), ensure_ascii=True)
    row.analysis_json_path = relative_to_root(analysis_path)
    row.preprocessing_warnings_json = json.dumps(analysis.get("warnings", []), ensure_ascii=True)
    boundary = analysis.get("card_boundary", {})
    row.auto_corners_json = json.dumps(boundary.get("auto_corners") or [], ensure_ascii=True)
    row.manual_corners_json = json.dumps(boundary.get("manual_corners") or [], ensure_ascii=True)
    row.final_corners_json = json.dumps(boundary.get("final_corners") or [], ensure_ascii=True)
    row.boundary_source = boundary.get("boundary_source")
    row.boundary_confidence = boundary.get("confidence")
    row.centering_json = json.dumps(analysis.get("centering", {}), ensure_ascii=True)
    row.error_message = "; ".join(analysis.get("warnings", []))[:500] if analysis.get("status") == "failed" else None
    row.updated_at = datetime.utcnow()
    row.completed_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def failed_analysis(card_id: int, side: str, warning: str, output_dir: Path) -> dict[str, Any]:
    return {
        "card_id": str(card_id),
        "side": side,
        "preprocessing_version": PREPROCESSING_VERSION,
        "status": "failed",
        "generated_at": utc_iso(),
        "card_boundary": {
            "detected": False,
            "boundary_source": "fallback",
            "confidence": 0.0,
            "auto_corners": [],
            "manual_corners": [],
            "final_corners": [],
        },
        "centering": {"detected": False, "confidence": 0.0, "warnings": [warning]},
        "generated_images": {},
        "warnings": [warning],
        "output_dir": relative_to_root(output_dir),
    }


def write_analysis_json(output_dir: Path, analysis: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = output_dir / "analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return analysis_path


def preprocess_side(
    session: Session,
    owned_card_id: int,
    side: str,
    manual_corners: list[list[float]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    media = latest_side_media(session, owned_card_id, side)
    output_dir = MEDIA_DIR / "processed" / str(owned_card_id) / side
    if media is None:
        analysis = failed_analysis(owned_card_id, side, f"no {side} image uploaded", output_dir)
        path = write_analysis_json(output_dir, analysis)
        upsert_processed_side(session, owned_card_id, side, None, analysis, path)
        return analysis

    try:
        previous = latest_processed_side(session, owned_card_id, side)
        if manual_corners is None and ENABLE_MANUAL_CENTERING_CORRECTION and previous is not None:
            previous_manual = json_loads(previous.manual_corners_json, [])
            manual_corners = previous_manual if previous_manual else None

        source_path = resolve_media_path(media.file_path)
        original = read_source_image(source_path)
        normalized = normalize_original(original)
        height, width = normalized.shape[:2]
        warnings: list[str] = []

        if ENABLE_CENTERING_DETECTION:
            auto_detection = detect_card_boundary(normalized)
        else:
            auto_detection = {
                "detected": False,
                "confidence": 0.0,
                "auto_corners": [],
                "warnings": ["automatic centering detection disabled"],
            }
        warnings.extend(auto_detection.get("warnings", []))

        auto_corners = auto_detection.get("auto_corners") or []
        manual_corners_ordered = order_corners(manual_corners) if manual_corners else []
        if manual_corners_ordered:
            final_corners = manual_corners_ordered
            boundary_source = "manual"
            boundary_confidence = max(float(auto_detection.get("confidence", 0.0)), 0.75)
        elif auto_detection.get("detected") and auto_corners:
            final_corners = order_corners(auto_corners)
            boundary_source = "auto"
            boundary_confidence = float(auto_detection.get("confidence", 0.0))
        else:
            final_corners = fallback_corners(width, height)
            boundary_source = "fallback"
            boundary_confidence = 0.0
            warnings.append("automatic boundary detection failed; using full image fallback")

        generated_paths = {
            "original_normalized": output_dir / "original_normalized.jpg",
            "grayscale_clahe": output_dir / "grayscale_clahe.jpg",
            "sobel_edges": output_dir / "sobel_edges.jpg",
            "emboss_surface": output_dir / "emboss_surface.jpg",
            "highpass_texture": output_dir / "highpass_texture.jpg",
            "canny_edges": output_dir / "canny_edges.jpg",
            "perspective_corrected": output_dir / "perspective_corrected.jpg",
            "centering_debug": output_dir / "centering_debug.jpg",
        }

        write_image(generated_paths["original_normalized"], normalized)
        write_image(generated_paths["grayscale_clahe"], clahe_gray(normalized))
        write_image(generated_paths["sobel_edges"], sobel_edges(normalized))
        write_image(generated_paths["emboss_surface"], emboss_surface(normalized))
        write_image(generated_paths["highpass_texture"], highpass_texture(normalized))
        write_image(generated_paths["canny_edges"], canny_edges(normalized))

        try:
            perspective = warp_card_to_standard(normalized, final_corners)
        except cv2.error as exc:
            warnings.append(f"perspective correction failed: {exc}")
            perspective = cv2.resize(normalized, (1000, 1400), interpolation=cv2.INTER_AREA)
        write_image(generated_paths["perspective_corrected"], perspective)

        layout_profile = "pokemon_front" if side == "front" else "pokemon_back" if side == "back" else "generic"
        centering = calculate_centering_from_warped_card(perspective, side=side, layout_profile=layout_profile) if ENABLE_CENTERING_DETECTION else {
            "detected": False,
            "confidence": 0.0,
            "warnings": ["centering calculation disabled"],
        }
        warnings.extend(centering.get("warnings", []))
        boundary = {
            "detected": bool(auto_detection.get("detected")),
            "boundary_source": boundary_source,
            "confidence": round(boundary_confidence, 2),
            "auto_corners": order_corners(auto_corners) if auto_corners else [],
            "manual_corners": manual_corners_ordered,
            "final_corners": order_corners(final_corners),
        }
        write_image(generated_paths["centering_debug"], draw_centering_debug(perspective, centering, boundary))

        analysis = {
            "card_id": str(owned_card_id),
            "side": side,
            "preprocessing_version": PREPROCESSING_VERSION,
            "status": "completed",
            "generated_at": utc_iso(),
            "processing_duration_seconds": round(time.perf_counter() - started, 3),
            "source_media_id": media.id,
            "source_image": media.file_path,
            "normalized_width": width,
            "normalized_height": height,
            "card_boundary": boundary,
            "centering": centering,
            "generated_images": {key: relative_to_root(path) for key, path in generated_paths.items()},
            "warnings": sorted(set(warnings)),
        }
        analysis_path = write_analysis_json(output_dir, analysis)
        upsert_processed_side(session, owned_card_id, side, media.id, analysis, analysis_path)
        logger.info(
            "Preprocessed card side owned_card_id=%s side=%s duration=%.3fs warnings=%s",
            owned_card_id,
            side,
            time.perf_counter() - started,
            len(warnings),
        )
        return analysis
    except Exception as exc:
        logger.exception("Preprocessing failed owned_card_id=%s side=%s", owned_card_id, side)
        analysis = failed_analysis(owned_card_id, side, f"preprocessing failed: {exc}", output_dir)
        path = write_analysis_json(output_dir, analysis)
        upsert_processed_side(session, owned_card_id, side, media.id, analysis, path)
        return analysis


def preprocess_owned_card(session: Session, owned_card_id: int) -> dict[str, Any]:
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    if not ENABLE_IMAGE_PREPROCESSING:
        return {
            "ok": False,
            "status": "disabled",
            "message": "Image preprocessing is disabled by ENABLE_IMAGE_PREPROCESSING=false.",
            "sides": {},
        }
    sides = {
        side: preprocess_side(session, owned_card_id, side)
        for side in ("front", "back")
        if latest_side_media(session, owned_card_id, side) is not None
    }
    if not sides:
        raise HTTPException(status_code=400, detail="No front or back image uploaded for this owned card.")
    return {"ok": True, "status": "completed", "owned_card_id": owned_card_id, "sides": sides}


def save_manual_boundary(
    session: Session,
    owned_card_id: int,
    side: str,
    manual_corners: list[list[float]],
) -> dict[str, Any]:
    if not ENABLE_MANUAL_CENTERING_CORRECTION:
        raise HTTPException(status_code=400, detail="Manual centering correction is disabled.")
    if side not in {"front", "back"}:
        raise HTTPException(status_code=400, detail="side must be front or back")
    if len(manual_corners) != 4:
        raise HTTPException(status_code=400, detail="manual_corners must contain four points")
    return preprocess_side(session, owned_card_id, side, manual_corners=manual_corners)


def recalculate_centering(session: Session, owned_card_id: int, side: str | None = None) -> dict[str, Any]:
    if side is not None and side not in {"front", "back"}:
        raise HTTPException(status_code=400, detail="side must be front or back")
    sides = [side] if side else ["front", "back"]
    return {
        "ok": True,
        "owned_card_id": owned_card_id,
        "sides": {
            item: preprocess_side(session, owned_card_id, item)
            for item in sides
            if latest_side_media(session, owned_card_id, item) is not None
        },
    }


def read_analysis_file(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    resolved = (ROOT / path).resolve()
    media_root = MEDIA_DIR.resolve()
    if resolved != media_root and media_root not in resolved.parents:
        return None
    if not resolved.is_file():
        return None
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def processed_payload(session: Session, owned_card_id: int) -> dict[str, Any]:
    rows = session.exec(
        select(ProcessedCardImage)
        .where(ProcessedCardImage.owned_card_id == owned_card_id)
        .order_by(ProcessedCardImage.side, ProcessedCardImage.updated_at.desc(), ProcessedCardImage.id.desc())
    ).all()
    latest_by_side: dict[str, ProcessedCardImage] = {}
    for row in rows:
        if row.side not in latest_by_side:
            latest_by_side[row.side] = row

    sides: dict[str, Any] = {}
    for side, row in latest_by_side.items():
        analysis = read_analysis_file(row.analysis_json_path) or {}
        sides[side] = {
            "id": row.id,
            "side": side,
            "status": row.status,
            "preprocessing_version": row.preprocessing_version,
            "analysis_json_path": row.analysis_json_path,
            "analysis": analysis,
            "generated_images": analysis.get("generated_images") or json_loads(row.generated_images_json, {}),
            "warnings": analysis.get("warnings") or json_loads(row.preprocessing_warnings_json, []),
            "card_boundary": analysis.get("card_boundary") or {
                "detected": bool(row.auto_corners_json),
                "boundary_source": row.boundary_source,
                "confidence": row.boundary_confidence,
                "auto_corners": json_loads(row.auto_corners_json, []),
                "manual_corners": json_loads(row.manual_corners_json, []),
                "final_corners": json_loads(row.final_corners_json, []),
            },
            "centering": analysis.get("centering") or json_loads(row.centering_json, {}),
            "updated_at": row.updated_at.isoformat(),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
    return {
        "ok": True,
        "owned_card_id": owned_card_id,
        "enabled": ENABLE_IMAGE_PREPROCESSING,
        "sides": sides,
    }
