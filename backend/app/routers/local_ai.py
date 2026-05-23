from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import AnalysisRunRead, LocalAIStatusRead
from ..services.local_ai import local_ai_status, run_local_ai_fast

router = APIRouter()


@router.get("/local-ai/status", response_model=LocalAIStatusRead)
def get_local_ai_status():
    return local_ai_status()


@router.post("/owned-cards/{owned_card_id}/analyze/local-ai-fast", response_model=AnalysisRunRead)
def analyze_owned_card_local_ai_fast(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_local_ai_fast(session, owned_card_id)
