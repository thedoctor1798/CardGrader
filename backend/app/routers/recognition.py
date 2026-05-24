from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import RecognitionAcceptRequest, RecognitionAcceptResponse, RecognitionResponse
from ..services.recognition import accept_recognition_candidate, recognize_media_card

router = APIRouter()


@router.post("/media/{media_id}/recognize-card", response_model=RecognitionResponse)
def recognize_card_from_media(media_id: int, session: Session = Depends(get_session)):
    return recognize_media_card(session, media_id)


@router.post("/recognition-attempts/{attempt_id}/accept", response_model=RecognitionAcceptResponse)
def accept_recognition_attempt(
    attempt_id: int,
    payload: RecognitionAcceptRequest,
    session: Session = Depends(get_session),
):
    return accept_recognition_candidate(
        session,
        attempt_id,
        payload.catalog_card_id,
        payload.owned_card_id,
        payload.create_owned_card,
    )
