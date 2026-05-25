from fastapi import HTTPException
import json
from sqlmodel import Session, select

from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun
from .centering import latest_manual_centering
from .pricing import get_latest_price_for_card
from .scoring import get_owned_card_and_card, is_confirmed_grade_limiter, load_opportunity, main_grade_limiter


def build_analysis_report(session: Session, analysis_run_id: int) -> dict:
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    owned_card, card = get_owned_card_and_card(session, analysis_run)
    latest_price = get_latest_price_for_card(session, card.id)
    latest_centering = latest_manual_centering(session, owned_card.id)
    opportunity = load_opportunity(session, card.id)
    assets = session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == analysis_run_id)
        .order_by(AnalysisAsset.created_at, AnalysisAsset.id)
    ).all()
    findings = session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == analysis_run_id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()
    limiter = main_grade_limiter(findings)
    confirmed_findings = [finding for finding in findings if is_confirmed_grade_limiter(finding)]
    uncertain_findings = [
        finding
        for finding in findings
        if (finding.finding_type or "").lower() in {"glare_uncertain", "image_quality_issue"}
    ]
    strengths = []
    if not confirmed_findings:
        strengths.append("A lokális AI nem jelölt egyértelmű, megerősített sérülést.")
    if latest_centering is not None:
        strengths.append(
            f"Manualis centering meres: L/R {latest_centering.horizontal_ratio_label}, "
            f"T/B {latest_centering.vertical_ratio_label}."
        )
    elif analysis_run.centering_score is not None and analysis_run.centering_score >= 8.5:
        strengths.append("A centering MVP pontszám erős előszűrési értéket mutat.")
    main_grade_limiters = [
        f"{finding.title or finding.finding_type or 'Finding'} ({finding.severity or 'unknown'}, {finding.location_label or 'ismeretlen hely'})"
        for finding in confirmed_findings[:5]
    ]
    if not main_grade_limiters and uncertain_findings:
        main_grade_limiters.append("Bizonytalan glare/képminőség jelzés, jobb fotóval ellenőrizendő.")
    if limiter is not None and main_grade_limiters:
        main_grade_limiters[0] = (
            f"Fő limiter: {limiter.title or limiter.finding_type or 'finding'} "
            f"({limiter.severity or 'unknown'}, {limiter.location_label or 'ismeretlen hely'})"
        )
    manual_review_recommendations = [
        "Ellenőrizd kézzel a sarok- és élkivágásokat nagyítva.",
        "A surface hibákat döntött fényben készített fotóval érdemes újranézni.",
    ]
    if uncertain_findings:
        manual_review_recommendations.append("A bizonytalan glare jelzésekhez készíts új képet egyenletesebb megvilágítással.")

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
        "warnings": json_list(analysis_run.warnings_json),
        "analysis_scope": analysis_run.analysis_scope,
        "image_labels_sent": json_list(analysis_run.image_labels_json),
        "allowed_issue_areas": json_list(analysis_run.allowed_areas_json),
        "image_payload": json_object_list(analysis_run.image_payload_json),
        "latest_price": latest_price,
        "latest_centering": latest_centering,
        "opportunity_precheck": opportunity,
        "assets": assets,
        "findings": findings,
        "strengths": strengths,
        "main_grade_limiters": main_grade_limiters,
        "manual_review_recommendations": manual_review_recommendations,
    }


def json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def json_object_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
