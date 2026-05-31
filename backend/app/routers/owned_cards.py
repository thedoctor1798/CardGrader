import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, delete, select

from ..config import MEDIA_DIR, ROOT
from ..database import get_session
from ..models import (
    AIGradingPipelineRun,
    AnalysisAsset,
    AnalysisFinding,
    AnalysisRun,
    Card,
    CardMedia,
    CenteringMeasurement,
    OwnedCard,
    PriceHistory,
    PriceObservation,
    ProcessedCardImage,
    RecognitionAttempt,
    RecognitionCandidate,
)
from ..models.core import utc_now
from ..schemas import OwnedCardCreate, OwnedCardDeleteResponse, OwnedCardRead, OwnedCardUpdate

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/owned-cards", response_model=List[OwnedCardRead])
def list_owned_cards(session: Session = Depends(get_session)):
    return session.exec(select(OwnedCard).order_by(OwnedCard.id)).all()


@router.post("/owned-cards", response_model=OwnedCardRead, status_code=201)
def create_owned_card(
    owned_card_in: OwnedCardCreate,
    session: Session = Depends(get_session),
):
    if session.get(Card, owned_card_in.card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")

    owned_card = OwnedCard(**owned_card_in.dict())
    session.add(owned_card)
    session.commit()
    session.refresh(owned_card)
    return owned_card


@router.get("/owned-cards/{owned_card_id}", response_model=OwnedCardRead)
def get_owned_card(owned_card_id: int, session: Session = Depends(get_session)):
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    return owned_card


@router.patch("/owned-cards/{owned_card_id}", response_model=OwnedCardRead)
def update_owned_card(
    owned_card_id: int,
    owned_card_in: OwnedCardUpdate,
    session: Session = Depends(get_session),
):
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    update_data = owned_card_in.dict(exclude_unset=True)
    if "card_id" in update_data and session.get(Card, update_data["card_id"]) is None:
        raise HTTPException(status_code=404, detail="Card not found")
    for key, value in update_data.items():
        setattr(owned_card, key, value)
    owned_card.updated_at = utc_now()
    session.add(owned_card)
    session.commit()
    session.refresh(owned_card)
    return owned_card


def safe_delete_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    path = (ROOT / file_path).resolve()
    media_root = MEDIA_DIR.resolve()
    if path == media_root or media_root not in path.parents:
        return False
    if not path.exists() or not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("Failed to delete media file %s: %s", path, exc)
        return False


def generated_paths(processed: ProcessedCardImage) -> list[str]:
    paths: list[str] = []
    for raw in (processed.generated_images_json,):
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            paths.extend(str(value) for value in parsed.values() if value)
    if processed.analysis_json_path:
        paths.append(processed.analysis_json_path)
    return paths


@router.delete("/owned-cards/{owned_card_id}", response_model=OwnedCardDeleteResponse)
def delete_owned_card(owned_card_id: int, session: Session = Depends(get_session)):
    owned_card = session.get(OwnedCard, owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    deleted: dict[str, int] = {}
    files: set[str] = set()

    media_rows = session.exec(select(CardMedia).where(CardMedia.owned_card_id == owned_card_id)).all()
    files.update(row.file_path for row in media_rows if row.file_path)

    analysis_runs = session.exec(select(AnalysisRun).where(AnalysisRun.owned_card_id == owned_card_id)).all()
    analysis_run_ids = [row.id for row in analysis_runs if row.id is not None]
    if analysis_run_ids:
        assets = session.exec(select(AnalysisAsset).where(AnalysisAsset.analysis_run_id.in_(analysis_run_ids))).all()
        files.update(row.file_path for row in assets if row.file_path)
        deleted["analysis_assets"] = len(assets)
        session.exec(delete(AnalysisAsset).where(AnalysisAsset.analysis_run_id.in_(analysis_run_ids)))
        deleted["analysis_findings"] = len(session.exec(select(AnalysisFinding).where(AnalysisFinding.analysis_run_id.in_(analysis_run_ids))).all())
        session.exec(delete(AnalysisFinding).where(AnalysisFinding.analysis_run_id.in_(analysis_run_ids)))
    else:
        deleted["analysis_assets"] = 0
        deleted["analysis_findings"] = 0

    processed_rows = session.exec(select(ProcessedCardImage).where(ProcessedCardImage.owned_card_id == owned_card_id)).all()
    for row in processed_rows:
        files.update(generated_paths(row))
    deleted["processed_card_images"] = len(processed_rows)
    session.exec(delete(ProcessedCardImage).where(ProcessedCardImage.owned_card_id == owned_card_id))

    attempts = session.exec(select(RecognitionAttempt).where(RecognitionAttempt.owned_card_id == owned_card_id)).all()
    attempt_ids = [row.id for row in attempts if row.id is not None]
    if attempt_ids:
        deleted["recognition_candidates"] = len(session.exec(select(RecognitionCandidate).where(RecognitionCandidate.recognition_attempt_id.in_(attempt_ids))).all())
        session.exec(delete(RecognitionCandidate).where(RecognitionCandidate.recognition_attempt_id.in_(attempt_ids)))
    else:
        deleted["recognition_candidates"] = 0
    deleted["recognition_attempts"] = len(attempts)
    session.exec(delete(RecognitionAttempt).where(RecognitionAttempt.owned_card_id == owned_card_id))

    deleted["ai_grading_pipeline_runs"] = len(session.exec(select(AIGradingPipelineRun).where(AIGradingPipelineRun.owned_card_id == owned_card_id)).all())
    session.exec(delete(AIGradingPipelineRun).where(AIGradingPipelineRun.owned_card_id == owned_card_id))
    deleted["centering_measurements"] = len(session.exec(select(CenteringMeasurement).where(CenteringMeasurement.owned_card_id == owned_card_id)).all())
    session.exec(delete(CenteringMeasurement).where(CenteringMeasurement.owned_card_id == owned_card_id))
    deleted["price_history"] = len(session.exec(select(PriceHistory).where(PriceHistory.owned_card_id == owned_card_id)).all())
    session.exec(delete(PriceHistory).where(PriceHistory.owned_card_id == owned_card_id))
    deleted["price_observations"] = len(session.exec(select(PriceObservation).where(PriceObservation.owned_card_id == owned_card_id)).all())
    session.exec(delete(PriceObservation).where(PriceObservation.owned_card_id == owned_card_id))

    if analysis_run_ids:
        deleted["analysis_runs"] = len(analysis_runs)
        session.exec(delete(AnalysisRun).where(AnalysisRun.id.in_(analysis_run_ids)))
    else:
        deleted["analysis_runs"] = 0

    deleted["card_media"] = len(media_rows)
    session.exec(delete(CardMedia).where(CardMedia.owned_card_id == owned_card_id))
    session.delete(owned_card)

    session.commit()
    deleted_files = 0
    for file_path in files:
        if safe_delete_file(file_path):
            deleted_files += 1
    return OwnedCardDeleteResponse(
        ok=True,
        deleted_owned_card_id=owned_card_id,
        deleted_files=deleted_files,
        deleted=deleted,
        message="Owned card and related local data deleted.",
    )
