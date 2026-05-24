from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import LocalAIConfigRead, LocalAIStatusRead, LocalAITestConnectionRead
from ..services.local_ai import (
    dry_run_local_ai,
    local_ai_config,
    local_ai_debug_single_image,
    local_ai_status,
    run_remote_ai_grade,
    run_local_ai_aggregate,
    run_local_ai_fast,
    run_local_ai_full_review,
    run_local_ai_pass,
    test_local_ai_connection,
)

router = APIRouter()


@router.get("/local-ai/status", response_model=LocalAIStatusRead)
def get_local_ai_status():
    return local_ai_status()


@router.get("/local-ai/config", response_model=LocalAIConfigRead)
def get_local_ai_config():
    return local_ai_config()


@router.post("/local-ai/test-connection", response_model=LocalAITestConnectionRead)
def test_connection():
    return test_local_ai_connection()


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-fast")
def analyze_owned_card_local_ai_fast(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_fast(session, owned_card_id)


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-front")
def analyze_owned_card_local_ai_front(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_pass(session, owned_card_id, "front")


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-back")
def analyze_owned_card_local_ai_back(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_pass(session, owned_card_id, "back")


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-aggregate")
def analyze_owned_card_local_ai_aggregate(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_aggregate(session, owned_card_id)


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-full-review")
def analyze_owned_card_local_ai_full_review(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_full_review(session, owned_card_id)


@router.post("/owned-cards/{owned_card_id}/analyze/remote-ai-grade")
def analyze_owned_card_remote_ai_grade(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_remote_ai_grade(session, owned_card_id)


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-dry-run")
def analyze_owned_card_local_ai_dry_run(
    owned_card_id: int,
    pass_type: str = "fast",
    session: Session = Depends(get_session),
):
    return dry_run_local_ai(session, owned_card_id, pass_type)


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-debug-single-image")
def analyze_owned_card_local_ai_debug_single_image(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return local_ai_debug_single_image(session, owned_card_id)
