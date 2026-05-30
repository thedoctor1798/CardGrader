from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..database import get_session
from ..services.ai_grading_pipeline import (
    get_pipeline_result,
    get_pipeline_status,
    retry_phase_b,
    run_two_phase_ai_grading,
)
from ..services.image_preprocessing import (
    preprocess_owned_card,
    processed_payload,
    recalculate_centering,
    save_manual_boundary,
)

router = APIRouter()


class BoundaryCorrectionRequest(BaseModel):
    side: str
    manual_corners: list[list[float]] = Field(min_items=4, max_items=4)


class CenteringRecalculateRequest(BaseModel):
    side: str | None = None


@router.get("/cards/{card_id}/processed")
def get_processed_images(
    card_id: int,
    session: Session = Depends(get_session),
):
    return processed_payload(session, card_id)


@router.post("/cards/{card_id}/preprocess")
def run_preprocessing(
    card_id: int,
    session: Session = Depends(get_session),
):
    return preprocess_owned_card(session, card_id)


@router.post("/cards/{card_id}/boundary")
def save_boundary(
    card_id: int,
    payload: BoundaryCorrectionRequest,
    session: Session = Depends(get_session),
):
    return save_manual_boundary(session, card_id, payload.side, payload.manual_corners)


@router.post("/cards/{card_id}/centering/recalculate")
def recalculate_card_centering(
    card_id: int,
    payload: CenteringRecalculateRequest | None = None,
    session: Session = Depends(get_session),
):
    return recalculate_centering(session, card_id, payload.side if payload else None)


@router.post("/cards/{card_id}/ai-grade/start")
def start_ai_grading(
    card_id: int,
    session: Session = Depends(get_session),
):
    return run_two_phase_ai_grading(session, card_id)


@router.post("/cards/{card_id}/ai-grade/retry-phase-b")
def retry_ai_grading_phase_b(
    card_id: int,
    session: Session = Depends(get_session),
):
    return retry_phase_b(session, card_id)


@router.get("/cards/{card_id}/ai-grade/status")
def get_ai_grading_status(
    card_id: int,
    session: Session = Depends(get_session),
):
    return get_pipeline_status(session, card_id)


@router.get("/cards/{card_id}/ai-grade/result")
def get_ai_grading_result(
    card_id: int,
    session: Session = Depends(get_session),
):
    return get_pipeline_result(session, card_id)
