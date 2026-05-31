import cv2
import numpy as np
from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import CenteringMeasurement, OwnedCard
from ..schemas.centering import CenteringMeasurementCreate


def clamp_line(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def ratio_label(first: float, second: float) -> str:
    return f"{round(first):.0f}/{round(second):.0f}"


def ratio_parts(first_px: float, second_px: float) -> tuple[float, float, float]:
    total = first_px + second_px
    if total <= 0:
        raise HTTPException(status_code=400, detail="Border widths must be positive.")
    first = first_px * 100.0 / total
    second = second_px * 100.0 / total
    offcenter = abs(first - 50.0)
    return round(first, 2), round(second, 2), round(offcenter, 2)


def grade_from_limiter(limiter_percent: float) -> tuple[str, float]:
    if limiter_percent <= 55:
        return "Gem Mint 10", 10.0
    if limiter_percent <= 60:
        return "Mint 9", 9.0
    if limiter_percent <= 65:
        return "NM-MT 8.5", 8.5
    if limiter_percent <= 70:
        return "NM-MT 8", 8.0
    if limiter_percent <= 75:
        return "EX-MT 7.5", 7.5
    score = max(1.0, 7.0 - ((limiter_percent - 75.0) / 5.0))
    return "Below 7", round(score, 1)


def calculate_centering(payload: CenteringMeasurementCreate) -> dict:
    if payload.image_width <= 0 or payload.image_height <= 0:
        raise HTTPException(status_code=400, detail="Image dimensions must be positive.")

    outer_left = clamp_line(payload.outer_left_px, 0, payload.image_width - 1)
    outer_right = clamp_line(payload.outer_right_px, 1, payload.image_width)
    outer_top = clamp_line(payload.outer_top_px, 0, payload.image_height - 1)
    outer_bottom = clamp_line(payload.outer_bottom_px, 1, payload.image_height)
    inner_left = clamp_line(payload.inner_left_px, outer_left, outer_right)
    inner_right = clamp_line(payload.inner_right_px, outer_left, outer_right)
    inner_top = clamp_line(payload.inner_top_px, outer_top, outer_bottom)
    inner_bottom = clamp_line(payload.inner_bottom_px, outer_top, outer_bottom)

    if not (outer_left < inner_left < inner_right < outer_right):
        raise HTTPException(status_code=400, detail="Horizontal guide lines must be ordered outer-left < inner-left < inner-right < outer-right.")
    if not (outer_top < inner_top < inner_bottom < outer_bottom):
        raise HTTPException(status_code=400, detail="Vertical guide lines must be ordered outer-top < inner-top < inner-bottom < outer-bottom.")

    left_border = inner_left - outer_left
    right_border = outer_right - inner_right
    top_border = inner_top - outer_top
    bottom_border = outer_bottom - inner_bottom
    left_percent, right_percent, horizontal_off = ratio_parts(left_border, right_border)
    top_percent, bottom_percent, vertical_off = ratio_parts(top_border, bottom_border)
    horizontal_limiter = max(left_percent, right_percent)
    vertical_limiter = max(top_percent, bottom_percent)
    estimated_grade, centering_score = grade_from_limiter(max(horizontal_limiter, vertical_limiter))

    return {
        "outer_left_px": round(outer_left, 2),
        "outer_right_px": round(outer_right, 2),
        "outer_top_px": round(outer_top, 2),
        "outer_bottom_px": round(outer_bottom, 2),
        "inner_left_px": round(inner_left, 2),
        "inner_right_px": round(inner_right, 2),
        "inner_top_px": round(inner_top, 2),
        "inner_bottom_px": round(inner_bottom, 2),
        "outer_left_pct": round(outer_left * 100.0 / payload.image_width, 4),
        "outer_right_pct": round(outer_right * 100.0 / payload.image_width, 4),
        "outer_top_pct": round(outer_top * 100.0 / payload.image_height, 4),
        "outer_bottom_pct": round(outer_bottom * 100.0 / payload.image_height, 4),
        "inner_left_pct": round(inner_left * 100.0 / payload.image_width, 4),
        "inner_right_pct": round(inner_right * 100.0 / payload.image_width, 4),
        "inner_top_pct": round(inner_top * 100.0 / payload.image_height, 4),
        "inner_bottom_pct": round(inner_bottom * 100.0 / payload.image_height, 4),
        "left_border_px": round(left_border, 2),
        "right_border_px": round(right_border, 2),
        "top_border_px": round(top_border, 2),
        "bottom_border_px": round(bottom_border, 2),
        "horizontal_left_percent": left_percent,
        "horizontal_right_percent": right_percent,
        "vertical_top_percent": top_percent,
        "vertical_bottom_percent": bottom_percent,
        "horizontal_ratio_label": ratio_label(left_percent, right_percent),
        "vertical_ratio_label": ratio_label(top_percent, bottom_percent),
        "horizontal_offcenter_percent": horizontal_off,
        "vertical_offcenter_percent": vertical_off,
        "centering_score": centering_score,
        "estimated_grade_label": estimated_grade,
    }


def create_centering_measurement(
    session: Session,
    owned_card_id: int,
    payload: CenteringMeasurementCreate,
) -> CenteringMeasurement:
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    if payload.side not in {"front", "back"}:
        raise HTTPException(status_code=400, detail="side must be front or back")
    calculated = calculate_centering(payload)
    measurement = CenteringMeasurement(
        owned_card_id=owned_card_id,
        analysis_run_id=payload.analysis_run_id,
        media_id=payload.media_id,
        side=payload.side,
        source=payload.source or "manual",
        image_label=payload.image_label,
        image_width=payload.image_width,
        image_height=payload.image_height,
        notes=payload.notes,
        **calculated,
    )
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement


def latest_manual_centering(session: Session, owned_card_id: int) -> CenteringMeasurement | None:
    return session.exec(
        select(CenteringMeasurement)
        .where(CenteringMeasurement.owned_card_id == owned_card_id)
        .where(CenteringMeasurement.source == "manual")
        .order_by(CenteringMeasurement.created_at.desc(), CenteringMeasurement.id.desc())
    ).first()


STANDARD_CARD_WIDTH = 1000
STANDARD_CARD_HEIGHT = 1400
STANDARD_CARD_RATIO = STANDARD_CARD_WIDTH / STANDARD_CARD_HEIGHT
MIN_CARD_AREA_RATIO = 0.18
CARD_RATIO_TOLERANCE = 0.22


def order_corners(points: np.ndarray | list[list[float]]) -> list[list[float]]:
    pts = np.asarray(points, dtype="float32").reshape(4, 2)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(4)
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return [[round(float(x), 2), round(float(y), 2)] for x, y in ordered]


def fallback_corners(width: int, height: int) -> list[list[float]]:
    return [
        [0.0, 0.0],
        [float(max(0, width - 1)), 0.0],
        [float(max(0, width - 1)), float(max(0, height - 1))],
        [0.0, float(max(0, height - 1))],
    ]


def _quad_dimensions(corners: list[list[float]]) -> tuple[float, float]:
    pts = np.asarray(corners, dtype="float32")
    tl, tr, br, bl = pts
    width_top = float(np.linalg.norm(tr - tl))
    width_bottom = float(np.linalg.norm(br - bl))
    height_left = float(np.linalg.norm(bl - tl))
    height_right = float(np.linalg.norm(br - tr))
    return max(width_top, width_bottom), max(height_left, height_right)


def _boundary_confidence(
    corners: list[list[float]],
    contour_area: float,
    image_width: int,
    image_height: int,
    rectangular: bool,
) -> float:
    quad_width, quad_height = _quad_dimensions(corners)
    if quad_width <= 0 or quad_height <= 0:
        return 0.0
    area_ratio = min(1.0, contour_area / max(1.0, image_width * image_height))
    observed_ratio = min(quad_width, quad_height) / max(quad_width, quad_height)
    expected_ratio = min(STANDARD_CARD_RATIO, 1 / STANDARD_CARD_RATIO)
    ratio_penalty = min(1.0, abs(observed_ratio - expected_ratio) / CARD_RATIO_TOLERANCE)
    confidence = 0.35 + (area_ratio * 0.45) + (0.2 if rectangular else 0.05) - (ratio_penalty * 0.35)
    return round(max(0.0, min(0.99, confidence)), 2)


def _plausible_card_corners(corners: list[list[float]], contour_area: float, image_width: int, image_height: int) -> bool:
    if contour_area < image_width * image_height * MIN_CARD_AREA_RATIO:
        return False
    quad_width, quad_height = _quad_dimensions(corners)
    if quad_width <= 0 or quad_height <= 0:
        return False
    observed_ratio = min(quad_width, quad_height) / max(quad_width, quad_height)
    expected_ratio = min(STANDARD_CARD_RATIO, 1 / STANDARD_CARD_RATIO)
    return abs(observed_ratio - expected_ratio) <= CARD_RATIO_TOLERANCE


def detect_card_boundary(image: np.ndarray) -> dict:
    warnings: list[str] = []
    if image is None or image.size == 0:
        return {"detected": False, "confidence": 0.0, "auto_corners": [], "warnings": ["empty image"]}

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"detected": False, "confidence": 0.0, "auto_corners": [], "warnings": ["no external contours found"]}

    best: tuple[list[list[float]], float, bool] | None = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
        area = float(cv2.contourArea(contour))
        if area < width * height * MIN_CARD_AREA_RATIO:
            continue
        perimeter = cv2.arcLength(contour, True)
        for epsilon in (0.015, 0.025, 0.035, 0.05, 0.07):
            approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
            if len(approx) != 4:
                continue
            corners = order_corners(approx)
            if _plausible_card_corners(corners, area, width, height):
                best = (corners, area, True)
                break
        if best is not None:
            break

    if best is None:
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            area = float(cv2.contourArea(contour))
            rect = cv2.minAreaRect(contour)
            corners = order_corners(cv2.boxPoints(rect))
            if _plausible_card_corners(corners, area, width, height):
                best = (corners, area, False)
                warnings.append("used minimum area rectangle fallback")
                break

    if best is None:
        return {
            "detected": False,
            "confidence": 0.0,
            "auto_corners": [],
            "warnings": ["no plausible trading-card rectangle found"],
        }

    corners, area, rectangular = best
    return {
        "detected": True,
        "confidence": _boundary_confidence(corners, area, width, height, rectangular),
        "auto_corners": corners,
        "warnings": warnings,
    }


def warp_card_to_standard(
    image: np.ndarray,
    corners: list[list[float]],
    width: int = STANDARD_CARD_WIDTH,
    height: int = STANDARD_CARD_HEIGHT,
) -> np.ndarray:
    source = np.asarray(order_corners(corners), dtype="float32")
    target = np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(image, matrix, (width, height))


def _edge_position(projection: np.ndarray, start: int, stop: int) -> tuple[int, float]:
    start = max(0, min(len(projection) - 1, start))
    stop = max(start + 1, min(len(projection), stop))
    window = projection[start:stop]
    if window.size == 0:
        return start, 0.0
    index = int(np.argmax(window)) + start
    score = float(window[index - start])
    return index, score


def _candidate_horizontal_lines(
    gray: np.ndarray,
    edges: np.ndarray,
    left: int,
    right: int,
    start: int,
    stop: int,
    expected_y: int,
) -> list[dict]:
    height, width = gray.shape[:2]
    x0 = max(0, min(width - 2, left + int(width * 0.015)))
    x1 = max(x0 + 20, min(width - 1, right - int(width * 0.015)))
    span = max(1, x1 - x0)
    rows: list[dict] = []
    for y in range(max(2, start), min(height - 3, stop)):
        band = edges[y - 2 : y + 3, x0:x1]
        columns_hit = np.count_nonzero(band.max(axis=0))
        continuity = columns_hit / span
        if continuity < 0.12:
            continue
        upper = gray[max(0, y - 5) : y - 1, x0:x1]
        lower = gray[y + 1 : min(height, y + 5), x0:x1]
        contrast = abs(float(np.mean(upper)) - float(np.mean(lower))) / 80.0 if upper.size and lower.size else 0.0
        left_anchor = np.count_nonzero(edges[y - 3 : y + 4, max(0, x0 - 18) : min(width, x0 + 42)]) / max(1, 7 * 60)
        right_anchor = np.count_nonzero(edges[y - 3 : y + 4, max(0, x1 - 42) : min(width, x1 + 18)]) / max(1, 7 * 60)
        expected = 1.0 - min(1.0, abs(y - expected_y) / max(1, stop - start))
        outer_distance = min(1.0, max(0.0, min(y, height - 1 - y) / (height * 0.08)))
        score = (continuity * 0.42) + (min(1.0, contrast) * 0.18) + (expected * 0.22) + (min(1.0, left_anchor + right_anchor) * 0.12) + (outer_distance * 0.06)
        rows.append(
            {
                "position": int(y),
                "score": round(float(score), 4),
                "continuity": round(float(continuity), 4),
                "contrast": round(float(contrast), 4),
                "anchor": round(float(left_anchor + right_anchor), 4),
            }
        )
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows[:10]


def _select_horizontal_candidate(candidates: list[dict], min_score: float = 0.32, min_continuity: float = 0.22) -> tuple[int | None, float]:
    for candidate in candidates:
        if candidate["score"] >= min_score and candidate["continuity"] >= min_continuity:
            return int(candidate["position"]), float(candidate["score"])
    return None, float(candidates[0]["score"]) if candidates else 0.0


def _inner_border_edges(image: np.ndarray, side: str = "front", layout_profile: str | None = None) -> tuple[int, int, int, int, float, list[str], dict]:
    warnings: list[str] = []
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(clahe, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 145)
    y0, y1 = int(height * 0.08), int(height * 0.92)
    x0, x1 = int(width * 0.08), int(width * 0.92)
    vertical_projection = edges[y0:y1, :].sum(axis=0).astype("float32")

    left, left_score = _edge_position(vertical_projection, int(width * 0.04), int(width * 0.32))
    right, right_score = _edge_position(vertical_projection, int(width * 0.68), int(width * 0.96))

    expected_left = int(width * 0.08)
    expected_right = int(width * 0.92)
    if right <= left:
        warnings.append("vertical inner border detection uncertain; used proportional vertical guides")
        left, right = expected_left, expected_right
    profile = layout_profile or ("pokemon_front" if side == "front" else "pokemon_back" if side == "back" else "generic")
    if profile == "pokemon_front":
        top_zone = (int(height * 0.05), int(height * 0.25))
        bottom_zone = (int(height * 0.75), int(height * 0.98))
        expected_top = int(height * 0.065)
        expected_bottom = int(height * 0.94)
    else:
        top_zone = (int(height * 0.04), int(height * 0.28))
        bottom_zone = (int(height * 0.72), int(height * 0.97))
        expected_top = int(height * 0.08)
        expected_bottom = int(height * 0.92)

    top_candidates = _candidate_horizontal_lines(clahe, edges, left, right, top_zone[0], top_zone[1], expected_top)
    bottom_candidates = _candidate_horizontal_lines(clahe, edges, left, right, bottom_zone[0], bottom_zone[1], expected_bottom)
    top, top_score = _select_horizontal_candidate(top_candidates)
    bottom, bottom_score = _select_horizontal_candidate(bottom_candidates)
    horizontal_fallback = False
    if top is None:
        top = expected_top
        horizontal_fallback = True
    if bottom is None:
        bottom = expected_bottom
        horizontal_fallback = True
    if horizontal_fallback:
        warnings.append("Top/bottom inner frame detection uncertain")

    vertical_confidence = min(0.9, float(np.median([left_score, right_score])) / max(1.0, height * 255 * 0.018))
    horizontal_confidence = min(0.9, float(np.median([top_score, bottom_score])) if top_score or bottom_score else 0.16)
    confidence = min(vertical_confidence, horizontal_confidence)
    if horizontal_fallback:
        confidence = min(confidence, 0.35)
    if confidence < 0.18:
        warnings.append("inner border edge confidence low; used conservative fallback guides")
        confidence = 0.18

    debug = {
        "layout_profile": profile,
        "outer_card_boundary": {"left": 0, "right": width - 1, "top": 0, "bottom": height - 1},
        "inner_art_frame_boundary": {"left": int(left), "right": int(right), "top": int(top), "bottom": int(bottom)},
        "horizontal_candidates": {"top": top_candidates[:5], "bottom": bottom_candidates[:5]},
        "horizontal_fallback": horizontal_fallback,
        "search_zones": {"top": top_zone, "bottom": bottom_zone},
    }
    return left, right, int(top), int(bottom), round(float(confidence), 2), warnings, debug


def calculate_centering_from_warped_card(image: np.ndarray, side: str = "front", layout_profile: str | None = None) -> dict:
    if image is None or image.size == 0:
        return {
            "detected": False,
            "confidence": 0.0,
            "warnings": ["empty perspective corrected image"],
        }

    height, width = image.shape[:2]
    left, right, top, bottom, confidence, warnings, debug = _inner_border_edges(image, side=side, layout_profile=layout_profile)
    left_border = max(0, left)
    right_border = max(0, width - 1 - right)
    top_border = max(0, top)
    bottom_border = max(0, height - 1 - bottom)

    try:
        horizontal_left, horizontal_right, _ = ratio_parts(left_border, right_border)
        vertical_top, vertical_bottom, _ = ratio_parts(top_border, bottom_border)
    except HTTPException:
        return {
            "detected": False,
            "confidence": 0.0,
            "warnings": [*warnings, "could not calculate centering ratios"],
        }

    return {
        "detected": True,
        "confidence": confidence,
        "left_border_px": round(float(left_border), 2),
        "right_border_px": round(float(right_border), 2),
        "top_border_px": round(float(top_border), 2),
        "bottom_border_px": round(float(bottom_border), 2),
        "horizontal_ratio": ratio_label(horizontal_left, horizontal_right),
        "vertical_ratio": ratio_label(vertical_top, vertical_bottom),
        "horizontal_percent_left": horizontal_left,
        "horizontal_percent_right": horizontal_right,
        "vertical_percent_top": vertical_top,
        "vertical_percent_bottom": vertical_bottom,
        "inner_left_px": int(left),
        "inner_right_px": int(right),
        "inner_top_px": int(top),
        "inner_bottom_px": int(bottom),
        "outer_card_boundary": debug["outer_card_boundary"],
        "inner_art_frame_boundary": debug["inner_art_frame_boundary"],
        "auto_inner_frame": debug["inner_art_frame_boundary"],
        "manual_inner_frame": None,
        "final_inner_frame": debug["inner_art_frame_boundary"],
        "layout_profile": debug["layout_profile"],
        "debug_candidates": debug,
        "warnings": warnings,
    }


def draw_centering_debug(
    perspective_image: np.ndarray,
    centering: dict,
    boundary: dict,
) -> np.ndarray:
    debug = perspective_image.copy()
    height, width = debug.shape[:2]
    cv2.rectangle(debug, (0, 0), (width - 1, height - 1), (0, 255, 0), 4)
    cv2.putText(debug, "outer boundary", (20, height - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 0), 2)
    for point in [(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)]:
        cv2.circle(debug, point, 12, (0, 180, 255), -1)

    if centering.get("detected"):
        left = int(centering.get("inner_left_px", 0))
        right = int(centering.get("inner_right_px", width - 1))
        top = int(centering.get("inner_top_px", 0))
        bottom = int(centering.get("inner_bottom_px", height - 1))
        candidates = centering.get("debug_candidates", {}).get("horizontal_candidates", {})
        for candidate in candidates.get("top", []) + candidates.get("bottom", []):
            y = int(candidate.get("position", 0))
            color = (0, 220, 255) if candidate.get("score", 0) >= 0.32 else (60, 60, 220)
            cv2.line(debug, (left, y), (right, y), color, 1)
        cv2.rectangle(debug, (left, top), (right, bottom), (255, 255, 0), 3)
        cv2.putText(debug, "inner frame", (left + 10, max(28, top - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 0), 2)
        cv2.line(debug, (left, 0), (left, height), (255, 120, 0), 2)
        cv2.line(debug, (right, 0), (right, height), (255, 120, 0), 2)
        cv2.line(debug, (0, top), (width, top), (255, 120, 0), 2)
        cv2.line(debug, (0, bottom), (width, bottom), (255, 120, 0), 2)

    lines = [
        f"boundary: {boundary.get('boundary_source', 'auto')} conf={boundary.get('confidence', 0)}",
        f"H: {centering.get('horizontal_ratio', 'n/a')}  L={centering.get('left_border_px', '-')} R={centering.get('right_border_px', '-')}",
        f"V: {centering.get('vertical_ratio', 'n/a')}  T={centering.get('top_border_px', '-')} B={centering.get('bottom_border_px', '-')}",
        f"centering conf={centering.get('confidence', 0)}",
    ]
    y = 42
    for line in lines:
        cv2.putText(debug, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5)
        cv2.putText(debug, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        y += 42
    return debug
