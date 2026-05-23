from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, OwnedCard
from ..schemas import AnalysisRunDetailRead, AnalysisRunRead
from ..services.opencv_analysis import run_opencv_analysis

router = APIRouter()


@router.post("/owned-cards/{owned_card_id}/analyze/opencv", response_model=AnalysisRunRead)
def analyze_owned_card_opencv(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    return run_opencv_analysis(session, owned_card_id)


@router.get("/analysis-runs/{analysis_run_id}", response_model=AnalysisRunDetailRead)
def get_analysis_run(
    analysis_run_id: int,
    session: Session = Depends(get_session),
):
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    findings = session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == analysis_run_id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()
    assets = session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == analysis_run_id)
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    ).all()
    return {"analysis_run": analysis_run, "findings": findings, "assets": assets}


@router.get("/owned-cards/{owned_card_id}/analysis-runs", response_model=List[AnalysisRunRead])
def list_owned_card_analysis_runs(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")

    statement = (
        select(AnalysisRun)
        .where(AnalysisRun.owned_card_id == owned_card_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    )
    return session.exec(statement).all()
