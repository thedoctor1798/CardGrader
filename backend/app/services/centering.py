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
