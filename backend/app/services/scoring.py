from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import AnalysisFinding, AnalysisRun, Card, OwnedCard, PriceObservation
from .pricing import calculate_grading_opportunity, get_latest_price_for_card

SEVERITY_PENALTIES = {
    "very_minor": 0.3,
    "minor": 0.7,
    "moderate": 1.4,
    "severe": 2.8,
}
GRADE_IMPACT_MULTIPLIERS = {
    "none": 0.0,
    "low": 0.75,
    "medium": 1.0,
    "high": 1.25,
}
CORNER_FINDINGS = {"corner_whitening"}
EDGE_FINDINGS = {"edge_whitening"}
SURFACE_FINDINGS = {"scratch", "print_line", "dent", "stain", "surface_wear"}
UNCERTAIN_FINDINGS = {"image_quality_issue", "glare_uncertain"}


def require_completed_analysis_run(session: Session, analysis_run_id: int) -> AnalysisRun:
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if analysis_run.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis run must be completed before scoring")
    return analysis_run


def get_owned_card_and_card(session: Session, analysis_run: AnalysisRun) -> tuple[OwnedCard, Card]:
    owned_card = session.get(OwnedCard, analysis_run.owned_card_id)
    if owned_card is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    card = session.get(Card, owned_card.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return owned_card, card


def grade_range(overall_score: float) -> tuple[str, str]:
    if overall_score >= 9.4:
        return "PSA 9", "PSA 10"
    if overall_score >= 8.7:
        return "PSA 8", "PSA 9"
    if overall_score >= 8.0:
        return "PSA 7", "PSA 9"
    return "PSA 6", "PSA 8"


def probability_heuristic(overall_score: float) -> tuple[float, float, float, float]:
    if overall_score >= 9.4:
        return 25.0, 60.0, 13.0, 2.0
    if overall_score >= 8.7:
        return 8.0, 62.0, 25.0, 5.0
    if overall_score >= 8.0:
        return 2.0, 35.0, 45.0, 18.0
    return 0.0, 15.0, 45.0, 40.0


def load_findings(session: Session, analysis_run_id: int) -> list[AnalysisFinding]:
    return session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == analysis_run_id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()


def finding_penalty(finding: AnalysisFinding) -> float:
    severity = (finding.severity or "none").lower()
    impact = (finding.grade_impact or "medium").lower()
    return SEVERITY_PENALTIES.get(severity, 0.0) * GRADE_IMPACT_MULTIPLIERS.get(impact, 1.0)


def is_uncertain_only(finding: AnalysisFinding) -> bool:
    finding_type = (finding.finding_type or "unknown").lower()
    severity = (finding.severity or "none").lower()
    return finding_type in UNCERTAIN_FINDINGS and severity not in {"moderate", "severe"}


def is_confirmed_grade_limiter(finding: AnalysisFinding) -> bool:
    finding_type = (finding.finding_type or "unknown").lower()
    severity = (finding.severity or "none").lower()
    if severity in {"none", ""}:
        return False
    if finding_type in UNCERTAIN_FINDINGS:
        return severity in {"moderate", "severe"}
    return finding_type in CORNER_FINDINGS | EDGE_FINDINGS | SURFACE_FINDINGS


def apply_finding_penalties(
    corners_score: float,
    edges_score: float,
    surface_score: float,
    findings: list[AnalysisFinding],
) -> tuple[float, float, float]:
    for finding in findings:
        if is_uncertain_only(finding):
            continue
        finding_type = (finding.finding_type or "unknown").lower()
        penalty = finding_penalty(finding)
        if penalty <= 0:
            continue
        if finding_type in CORNER_FINDINGS:
            corners_score -= penalty
        elif finding_type in EDGE_FINDINGS:
            edges_score -= penalty
        elif finding_type in SURFACE_FINDINGS:
            surface_score -= penalty
        elif finding_type in UNCERTAIN_FINDINGS:
            surface_score -= penalty * 0.5
    return max(1.0, corners_score), max(1.0, edges_score), max(1.0, surface_score)


def probability_heuristic_with_findings(
    overall_score: float,
    surface_score: float,
    findings: list[AnalysisFinding],
) -> tuple[float, float, float, float]:
    psa_10, psa_9, psa_8, psa_7_or_lower = probability_heuristic(overall_score)
    confirmed = [finding for finding in findings if is_confirmed_grade_limiter(finding)]
    high_impact = any((finding.grade_impact or "").lower() == "high" for finding in confirmed)
    only_small_low_impact = bool(confirmed) and all(
        (finding.severity or "").lower() == "very_minor" and (finding.grade_impact or "").lower() in {"none", "low"}
        for finding in confirmed
    )

    if high_impact:
        psa_10 = min(psa_10, 10.0)
    elif only_small_low_impact:
        psa_10 = min(psa_10, 18.0)

    if surface_score < 8.5:
        reduction = 0.5 if surface_score >= 8.0 else 0.35
        psa_10 = round(psa_10 * reduction, 1)

    total_delta = 100.0 - (psa_10 + psa_9 + psa_8 + psa_7_or_lower)
    psa_9 += round(total_delta * 0.45, 1)
    psa_8 += round(total_delta * 0.35, 1)
    psa_7_or_lower = round(100.0 - psa_10 - psa_9 - psa_8, 1)
    return round(psa_10, 1), round(psa_9, 1), round(psa_8, 1), psa_7_or_lower


def severity_label(severity: str | None) -> str:
    labels = {
        "very_minor": "nagyon enyhe",
        "minor": "enyhe",
        "moderate": "közepes",
        "severe": "súlyos",
    }
    return labels.get((severity or "").lower(), "nem egyértelmű")


def main_grade_limiter(findings: list[AnalysisFinding]) -> AnalysisFinding | None:
    confirmed = [finding for finding in findings if is_confirmed_grade_limiter(finding)]
    if not confirmed:
        return None
    return max(confirmed, key=finding_penalty)


def findings_reduce_confidence(findings: list[AnalysisFinding]) -> bool:
    return any((finding.finding_type or "").lower() in UNCERTAIN_FINDINGS for finding in findings)


def load_opportunity(session: Session, card_id: int):
    try:
        return calculate_grading_opportunity(session, card_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


def recommendation_for(
    latest_price: PriceObservation | None,
    opportunity,
    overall_score: float,
) -> str:
    if latest_price is None:
        return "manual_review_needed"
    if opportunity is None:
        return "manual_review_needed"
    if opportunity.recommendation == "do_not_grade":
        return "do_not_grade"
    if opportunity.recommendation == "borderline_grade_candidate" and overall_score >= 8.5:
        return "borderline_grade_candidate"
    if opportunity.recommendation == "good_grade_candidate" and overall_score >= 8.5:
        return "good_grade_candidate"
    return "manual_review_needed"


def recommendation_reason_for(recommendation: str, opportunity) -> str:
    if recommendation == "do_not_grade":
        return (
            "A jelenlegi manuális ár-precheck alapján a grading költsége mellett nincs "
            "pozitív upside, ezért ez a lap most nem javasolt gradingre."
        )
    if recommendation == "good_grade_candidate":
        return (
            "Az árak alapján PSA 9 vagy jobb eredménynél pozitív upside látszik, és az "
            "OpenCV MVP scoring eléri a szükséges előszűrési szintet. Manuális sarok-, "
            "él- és surface review továbbra is szükséges."
        )
    if recommendation == "borderline_grade_candidate":
        minimum_grade = getattr(opportunity, "minimum_profitable_grade", None) or "PSA 10"
        return (
            f"Az árak alapján főleg {minimum_grade} esetén látszik upside, miközben az "
            "aktuális scoring még csak OpenCV előelemzésen alapul. Emiatt ez jelenleg "
            "borderline / bulk grade candidate, manuális sarok- és surface review mellett."
        )
    return (
        "Az elérhető adatok alapján még manuális ellenőrzés szükséges. A scoring lokális "
        "MVP előelemzés, nem hivatalos PSA grade és nem tartalmaz valódi defect felismerést."
    )


def human_summary_for(analysis_run: AnalysisRun, opportunity) -> str:
    summary = (
        "Ez egy lokális, API nélküli előelemzés. Az OpenCV pipeline alapján a centering "
        f"pontszám {analysis_run.centering_score}/10. A rendszer sarok- és élkivágásokat "
        "generált, de valódi whitening, karc vagy surface hiba felismerése ebben a "
        "fázisban még nem történik. "
        f"A jelenlegi becslés alapján a lap {analysis_run.estimated_grade_low}–"
        f"{analysis_run.estimated_grade_high} tartományba eshet, de manuális ellenőrzés "
        "szükséges. Ezek nem hivatalos PSA valószínűségek, hanem lokális MVP becslések."
    )
    if opportunity is not None:
        summary += (
            " Az ár-precheck alapján a minimum profitábilis grade: "
            f"{opportunity.minimum_profitable_grade}. Az aktuális recommendation: "
            f"{opportunity.recommendation}."
        )
    return summary


def human_summary_with_findings(
    analysis_run: AnalysisRun,
    opportunity,
    findings: list[AnalysisFinding],
) -> str:
    if not findings:
        return human_summary_for(analysis_run, opportunity)

    uncertain_only = all((finding.finding_type or "").lower() in UNCERTAIN_FINDINGS for finding in findings)
    limiter = main_grade_limiter(findings)
    if uncertain_only:
        summary = (
            f"A lokális AI {len(findings)} bizonytalan képi jelzést adott, főleg becsillanás vagy képminőség miatt. "
            "Ezeket a rendszer nem kezeli megerősített sérülésként; jobb megvilágítással készített front/back fotó "
            "javasolt a manuális ellenőrzéshez. "
        )
    elif limiter is not None:
        location = limiter.location_label or "ismeretlen régió"
        title = limiter.title or limiter.finding_type or "látható eltérés"
        summary = (
            f"A lokális AI {len(findings)} látható findingot jelölt. A fő grade-limiter egy "
            f"{severity_label(limiter.severity)} {title} a(z) {location} régióban. "
            "Ez csökkentheti a magas grade esélyét, de a becslés továbbra sem hivatalos grading eredmény. "
            "Manuális sarok-, él- és surface review javasolt. "
        )
    else:
        summary = (
            f"A lokális AI {len(findings)} findingot mentett, de nem talált erős, kategóriát limitáló sérülést. "
            "A jelenlegi pontszám lokális MVP előszűrés, manuális ellenőrzéssel érdemes megerősíteni. "
        )

    summary += (
        f"A jelenlegi becslés alapján a lap {analysis_run.estimated_grade_low}-"
        f"{analysis_run.estimated_grade_high} tartományba eshet."
    )
    if opportunity is not None:
        summary += (
            " Az ár-precheck alapján a minimum profitábilis grade: "
            f"{opportunity.minimum_profitable_grade}. Az aktuális recommendation: {opportunity.recommendation}."
        )
    return summary


def score_analysis_run(session: Session, analysis_run_id: int) -> AnalysisRun:
    analysis_run = require_completed_analysis_run(session, analysis_run_id)
    _, card = get_owned_card_and_card(session, analysis_run)

    latest_price = get_latest_price_for_card(session, card.id)
    opportunity = load_opportunity(session, card.id)
    findings = load_findings(session, analysis_run.id)
    low_confidence = analysis_run.confidence_level == "low"

    centering_score = analysis_run.centering_score if analysis_run.centering_score is not None else 8.0
    corners_score = 8.3 if low_confidence else 8.8
    edges_score = 8.3 if low_confidence else 8.8
    surface_score = 8.0 if low_confidence else 8.5
    if findings:
        corners_score, edges_score, surface_score = apply_finding_penalties(
            corners_score,
            edges_score,
            surface_score,
            findings,
        )
    overall_score = round(
        (centering_score * 0.30)
        + (corners_score * 0.25)
        + (edges_score * 0.20)
        + (surface_score * 0.25),
        1,
    )
    estimated_grade_low, estimated_grade_high = grade_range(overall_score)
    psa_10, psa_9, psa_8, psa_7_or_lower = probability_heuristic_with_findings(
        overall_score,
        surface_score,
        findings,
    )
    recommendation = recommendation_for(latest_price, opportunity, overall_score)
    confidence_level = "low" if low_confidence or findings_reduce_confidence(findings) else "medium"

    analysis_run.centering_score = round(float(centering_score), 1)
    analysis_run.corners_score = corners_score
    analysis_run.edges_score = edges_score
    analysis_run.surface_score = surface_score
    analysis_run.overall_score = overall_score
    analysis_run.estimated_grade_low = estimated_grade_low
    analysis_run.estimated_grade_high = estimated_grade_high
    analysis_run.psa_10_probability = psa_10
    analysis_run.psa_9_probability = psa_9
    analysis_run.psa_8_probability = psa_8
    analysis_run.psa_7_or_lower_probability = psa_7_or_lower
    analysis_run.confidence_level = confidence_level
    analysis_run.recommendation = recommendation
    analysis_run.recommendation_reason = recommendation_reason_for(recommendation, opportunity)
    analysis_run.human_summary = human_summary_with_findings(analysis_run, opportunity, findings)

    session.add(analysis_run)
    session.commit()
    session.refresh(analysis_run)
    return analysis_run
