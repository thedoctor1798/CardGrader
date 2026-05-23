from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import AnalysisAsset, AnalysisRun
from .pricing import get_latest_price_for_card
from .scoring import get_owned_card_and_card, load_opportunity


def build_analysis_report(session: Session, analysis_run_id: int) -> dict:
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    owned_card, card = get_owned_card_and_card(session, analysis_run)
    latest_price = get_latest_price_for_card(session, card.id)
    opportunity = load_opportunity(session, card.id)
    assets = session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == analysis_run_id)
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    ).all()

    return {
        "card": card,
        "owned_card": owned_card,
        "scores": {
            "centering_score": analysis_run.centering_score,
            "corners_score": analysis_run.corners_score,
            "edges_score": analysis_run.edges_score,
            "surface_score": analysis_run.surface_score,
            "overall_score": analysis_run.overall_score,
        },
        "probabilities": {
            "psa_10_probability": analysis_run.psa_10_probability,
            "psa_9_probability": analysis_run.psa_9_probability,
            "psa_8_probability": analysis_run.psa_8_probability,
            "psa_7_or_lower_probability": analysis_run.psa_7_or_lower_probability,
        },
        "estimated_grade_range": {
            "estimated_grade_low": analysis_run.estimated_grade_low,
            "estimated_grade_high": analysis_run.estimated_grade_high,
        },
        "confidence_level": analysis_run.confidence_level,
        "human_summary": analysis_run.human_summary,
        "recommendation": analysis_run.recommendation,
        "recommendation_reason": analysis_run.recommendation_reason,
        "latest_price": latest_price,
        "opportunity_precheck": opportunity,
        "assets": assets,
    }
