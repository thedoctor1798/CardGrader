from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import MEDIA_DIR, ROOT
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, CardMedia, OwnedCard

ANALYSIS_VERSION = "opencv_mvp_v3_resized_only"
NORMALIZED_WIDTH = 1000
NORMALIZED_HEIGHT = 1400
MIN_CARD_AREA_RATIO = 0.18
CARD_ASPECT_MIN = 0.52
CARD_ASPECT_MAX = 0.9
SUMMARY_HU = (
    "Lokalis OpenCV eloelemzes elkeszult. A rendszer resized front/back kepeket "
    "es alap kepminosegi metrikakat keszit. Az automatikus sarok- es elkivagasok "
    "a normal grading flow-ban jelenleg ki vannak kapcsolva, mert kezi ellenorzes "
    "nelkul megbizhatatlanok."
)


@dataclass
class ImageMetrics:
    width: int
    height: int
    sharpness_score: float
    brightness_mean: float
    contrast_score: float
    glare_risk: str
    glare_percent: float
    usable: bool
    centering_score: float
    border_ratios: Optional[dict[str, float]]


@dataclass
class NormalizationResult:
    normalized: Optional[np.ndarray]
    overlay: np.ndarray
    quad: Optional[np.ndarray]
    warning: Optional[str]


def relative_to_root(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def resolve_media_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    root = ROOT.resolve()
    media_root = MEDIA_DIR.resolve()
    if root not in path.parents or (path != media_root and media_root not in path.parents):
        raise HTTPException(status_code=400, detail="Invalid media path")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Media file missing: {relative_path}")
    return path


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail=f"Could not read image: {path.name}")
    return image


def write_jpeg(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not success:
        raise RuntimeError(f"Could not encode image: {path}")
    encoded.tofile(str(path))


def latest_image_media(session: Session, owned_card_id: int, label: str) -> Optional[CardMedia]:
    statement = (
        select(CardMedia)
        .where(CardMedia.owned_card_id == owned_card_id)
        .where(CardMedia.label == label)
        .where(CardMedia.media_type == "image")
        .order_by(CardMedia.created_at.desc(), CardMedia.id.desc())
    )
    return session.exec(statement).first()


def resize_for_analysis(image: np.ndarray, max_long_edge: int = 1600) -> np.ndarray:
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge <= max_long_edge:
        return image.copy()

    scale = max_long_edge / long_edge
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def order_quad_points(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype("float32")
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(4)
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return ordered


def quad_dimensions(quad: np.ndarray) -> tuple[float, float]:
    tl, tr, br, bl = quad
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)
    return max(width_top, width_bottom), max(height_left, height_right)


def is_plausible_card_quad(quad: np.ndarray, image_shape: tuple[int, int, int]) -> bool:
    height, width = image_shape[:2]
    area = float(cv2.contourArea(quad.astype("float32")))
    if area < width * height * MIN_CARD_AREA_RATIO:
        return False
    quad_width, quad_height = quad_dimensions(quad)
    if quad_width <= 0 or quad_height <= 0:
        return False
    ratio = min(quad_width, quad_height) / max(quad_width, quad_height)
    return CARD_ASPECT_MIN <= ratio <= CARD_ASPECT_MAX


def find_card_quad(image: np.ndarray) -> Optional[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        if cv2.contourArea(contour) < image.shape[0] * image.shape[1] * MIN_CARD_AREA_RATIO:
            continue
        perimeter = cv2.arcLength(contour, True)
        for epsilon in (0.015, 0.025, 0.035, 0.05):
            approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
            if len(approx) == 4:
                ordered = order_quad_points(approx)
                if is_plausible_card_quad(ordered, image.shape):
                    return ordered

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        ordered = order_quad_points(box)
        if is_plausible_card_quad(ordered, image.shape):
            return ordered
    return None


def warp_card(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    source = order_quad_points(quad)
    target = np.array(
        [
            [0, 0],
            [NORMALIZED_WIDTH - 1, 0],
            [NORMALIZED_WIDTH - 1, NORMALIZED_HEIGHT - 1],
            [0, NORMALIZED_HEIGHT - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(image, matrix, (NORMALIZED_WIDTH, NORMALIZED_HEIGHT))


def contour_overlay(image: np.ndarray, quad: Optional[np.ndarray], warning: Optional[str]) -> np.ndarray:
    overlay = image.copy()
    if quad is not None:
        points = order_quad_points(quad).astype(int).reshape((-1, 1, 2))
        cv2.polylines(overlay, [points], True, (0, 255, 0), 4)
        for index, point in enumerate(points.reshape(4, 2), start=1):
            cv2.circle(overlay, tuple(point), 8, (0, 180, 255), -1)
            cv2.putText(overlay, str(index), tuple(point + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2)
    if warning:
        cv2.putText(overlay, warning[:80], (24, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 80, 255), 2)
    return overlay


def normalize_card_image(image: np.ndarray) -> NormalizationResult:
    quad = find_card_quad(image)
    if quad is None:
        warning = "card contour not found"
        return NormalizationResult(None, contour_overlay(image, None, warning), None, warning)
    try:
        normalized = warp_card(image, quad)
    except cv2.error as exc:
        warning = f"card normalization failed: {exc}"
        return NormalizationResult(None, contour_overlay(image, quad, warning), quad, warning)
    return NormalizationResult(normalized, contour_overlay(image, quad, None), quad, None)


def glare_risk_from_percent(glare_percent: float) -> str:
    if glare_percent >= 5.0:
        return "high"
    if glare_percent >= 1.0:
        return "medium"
    return "low"


def estimate_border_ratios(image: np.ndarray) -> Optional[dict[str, float]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    height, width = image.shape[:2]
    image_area = width * height
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in candidates[:5]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.45:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approx) < 4 or len(approx) > 6:
            continue
        x, y, rect_width, rect_height = cv2.boundingRect(approx)
        if rect_width <= 0 or rect_height <= 0:
            continue
        return {
            "left": round(x / width, 4),
            "right": round((width - (x + rect_width)) / width, 4),
            "top": round(y / height, 4),
            "bottom": round((height - (y + rect_height)) / height, 4),
        }
    return None


def calculate_metrics(image: np.ndarray) -> ImageMetrics:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    glare_percent = float((gray >= 245).sum() * 100.0 / gray.size)
    glare_risk = glare_risk_from_percent(glare_percent)

    centering_score = 8.5
    if sharpness < 50:
        centering_score -= 2.0
    if brightness < 45:
        centering_score -= 1.5
    if contrast < 20:
        centering_score -= 1.0
    if glare_risk == "high":
        centering_score -= 0.5
    centering_score = round(max(1.0, centering_score), 2)

    usable = sharpness >= 50 and brightness >= 45 and contrast >= 20
    return ImageMetrics(
        width=width,
        height=height,
        sharpness_score=round(sharpness, 2),
        brightness_mean=round(brightness, 2),
        contrast_score=round(contrast, 2),
        glare_risk=glare_risk,
        glare_percent=round(glare_percent, 2),
        usable=usable,
        centering_score=centering_score,
        border_ratios=estimate_border_ratios(image),
    )


def crop_regions(image: np.ndarray) -> dict[str, np.ndarray]:
    height, width = image.shape[:2]
    corner_width = max(1, int(width * 0.28))
    corner_height = max(1, int(height * 0.22))
    edge_y = max(1, int(height * 0.16))
    edge_x = max(1, int(width * 0.16))

    return {
        "corner_tl": image[0:corner_height, 0:corner_width],
        "corner_tr": image[0:corner_height, width - corner_width : width],
        "corner_bl": image[height - corner_height : height, 0:corner_width],
        "corner_br": image[height - corner_height : height, width - corner_width : width],
        "edge_top": image[0:edge_y, :],
        "edge_right": image[:, width - edge_x : width],
        "edge_bottom": image[height - edge_y : height, :],
        "edge_left": image[:, 0:edge_x],
    }


def crop_is_valid(crop: np.ndarray) -> bool:
    if crop is None or crop.size == 0:
        return False
    height, width = crop.shape[:2]
    if height < 60 or width < 60:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    std = float(gray.std())
    return not (std < 0.5 and (mean < 3.0 or mean > 252.0))


def add_asset(session: Session, analysis_run_id: int, asset_type: str, label: str, path: Path) -> None:
    session.add(
        AnalysisAsset(
            analysis_run_id=analysis_run_id,
            asset_type=asset_type,
            label=label,
            file_path=relative_to_root(path),
        )
    )


def add_metrics_finding(
    session: Session,
    analysis_run_id: int,
    media_id: int,
    label: str,
    metrics: ImageMetrics,
) -> None:
    border_text = "border_ratios=null"
    if metrics.border_ratios is not None:
        border_text = (
            "border_ratios="
            f"left:{metrics.border_ratios['left']}, "
            f"right:{metrics.border_ratios['right']}, "
            f"top:{metrics.border_ratios['top']}, "
            f"bottom:{metrics.border_ratios['bottom']}"
        )

    session.add(
        AnalysisFinding(
            analysis_run_id=analysis_run_id,
            media_id=media_id,
            finding_type="image_quality",
            severity="info" if metrics.usable else "warning",
            confidence=0.7 if metrics.usable else 0.45,
            location_label=label,
            title=f"{label} image quality metrics",
            description=(
                f"width={metrics.width}, height={metrics.height}, "
                f"sharpness_score={metrics.sharpness_score}, "
                f"brightness_mean={metrics.brightness_mean}, "
                f"contrast_score={metrics.contrast_score}, "
                f"glare_risk={metrics.glare_risk}, "
                f"glare_percent={metrics.glare_percent}, {border_text}"
            ),
            grade_impact=None if metrics.usable else "low",
            side=label if label in {"front", "back"} else "unknown",
            confirmed=False,
            uncertainty_reason=None if metrics.usable else "Image quality reduced OpenCV confidence.",
            photo_quality_issue=not metrics.usable,
        )
    )


def add_preprocessing_warning(
    session: Session,
    analysis_run_id: int,
    media_id: int,
    label: str,
    title: str,
    description: str,
) -> None:
    session.add(
        AnalysisFinding(
            analysis_run_id=analysis_run_id,
            media_id=media_id,
            finding_type="image_quality_issue",
            severity="minor",
            confidence=0.65,
            location_label=label,
            title=title,
            description=description,
            grade_impact="low",
            side=label if label in {"front", "back"} else "unknown",
            confirmed=False,
            uncertainty_reason=description,
            photo_quality_issue=True,
        )
    )


def process_media_image(session: Session, analysis_run: AnalysisRun, media: CardMedia) -> ImageMetrics:
    label = media.label or "image"
    source_path = resolve_media_path(media.file_path)
    image = read_image(source_path)
    resized = resize_for_analysis(image)
    metrics = calculate_metrics(resized)

    resized_path = MEDIA_DIR / "resized" / str(analysis_run.id) / f"{label}_resized.jpg"
    write_jpeg(resized_path, resized)
    add_asset(session, analysis_run.id, "resized_image", f"{label}_resized", resized_path)

    add_metrics_finding(session, analysis_run.id, media.id, label, metrics)
    return metrics


def run_opencv_analysis(session: Session, owned_card_id: int) -> AnalysisRun:
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    media_items = [
        media
        for media in (
            latest_image_media(session, owned_card_id, "front"),
            latest_image_media(session, owned_card_id, "back"),
        )
        if media is not None
    ]
    if not media_items:
        raise HTTPException(
            status_code=400,
            detail="No front or back image uploaded for this owned card.",
        )

    analysis_run = AnalysisRun(
        owned_card_id=owned_card_id,
        mode="local_only",
        status="running",
        model_provider="none",
        model_name=None,
        prompt_version=None,
        opencv_version=cv2.__version__,
        analysis_version=ANALYSIS_VERSION,
    )
    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)

    try:
        metrics = [process_media_image(session, analysis_run, media) for media in media_items]
        centering_scores = [item.centering_score for item in metrics]
        quality_usable = all(item.usable for item in metrics)

        analysis_run.status = "completed"
        analysis_run.centering_score = round(sum(centering_scores) / len(centering_scores), 2)
        analysis_run.confidence_level = "medium" if quality_usable else "low"
        analysis_run.human_summary = SUMMARY_HU
        analysis_run.recommendation = "opencv_precheck_completed"
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        return analysis_run
    except Exception as exc:
        analysis_run.status = "failed"
        analysis_run.error_message = str(exc)
        analysis_run.completed_at = datetime.utcnow()
        session.add(analysis_run)
        session.commit()
        session.refresh(analysis_run)
        return analysis_run
