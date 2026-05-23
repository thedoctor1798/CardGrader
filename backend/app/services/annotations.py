from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageDraw
from sqlmodel import Session, select

from ..config import MEDIA_DIR, ROOT
from ..models import AnalysisAsset, AnalysisFinding, AnalysisRun, CardMedia

PHYSICAL_FINDING_TYPES = {"corner_whitening", "edge_whitening", "scratch", "print_line", "dent", "stain", "surface_wear"}
NON_ANNOTATED_FINDING_TYPES = {"glare_uncertain", "image_quality_issue", "unknown"}


def safe_project_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    root = ROOT.resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    return path


def latest_opencv_run_id(session: Session, owned_card_id: int, before_id: int) -> int | None:
    run = session.exec(
        select(AnalysisRun)
        .where(AnalysisRun.owned_card_id == owned_card_id)
        .where(AnalysisRun.status == "completed")
        .where(AnalysisRun.mode == "local_only")
        .where(AnalysisRun.id != before_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    ).first()
    return run.id if run else None


def candidate_assets(session: Session, analysis_run: AnalysisRun) -> list[AnalysisAsset]:
    run_ids = [analysis_run.id]
    opencv_run_id = latest_opencv_run_id(session, analysis_run.owned_card_id, analysis_run.id)
    if opencv_run_id is not None:
        run_ids.append(opencv_run_id)
    return session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id.in_(run_ids))
        .where(AnalysisAsset.asset_type.in_(["resized_image", "normalized_image", "crop"]))
        .order_by(AnalysisAsset.analysis_run_id.desc(), AnalysisAsset.asset_type.desc(), AnalysisAsset.id)
    ).all()


def finding_tokens(finding: AnalysisFinding) -> list[str]:
    text = " ".join(
        str(value or "").lower()
        for value in [finding.location_label, finding.finding_type, finding.title, finding.description]
    )
    tokens = []
    for token in [
        "front",
        "back",
        "corner_tl",
        "corner_tr",
        "corner_bl",
        "corner_br",
        "edge_top",
        "edge_right",
        "edge_bottom",
        "edge_left",
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    ]:
        if token in text:
            tokens.append(token)
    return tokens


def choose_source_asset(
    session: Session,
    analysis_run: AnalysisRun,
    finding: AnalysisFinding,
) -> AnalysisAsset | CardMedia | None:
    if finding.media_id is not None:
        media = session.get(CardMedia, finding.media_id)
        if media is not None:
            return media

    assets = candidate_assets(session, analysis_run)
    tokens = finding_tokens(finding)
    normalized_tokens = {
        "top_left": "corner_tl",
        "top_right": "corner_tr",
        "bottom_left": "corner_bl",
        "bottom_right": "corner_br",
    }
    tokens = [normalized_tokens.get(token, token) for token in tokens]

    for token in tokens:
        for asset in assets:
            label = (asset.label or "").lower()
            if token in label:
                return asset

    for side in ["front", "back"]:
        if side in tokens:
            for asset in assets:
                if asset.asset_type in {"normalized_image", "resized_image"} and side in (asset.label or "").lower():
                    return asset

    return next((asset for asset in assets if asset.asset_type == "normalized_image"), None) or next((asset for asset in assets if asset.asset_type == "resized_image"), None) or (assets[0] if assets else None)


def bbox_region(finding: AnalysisFinding, width: int, height: int) -> tuple[int, int, int, int] | None:
    x = int(finding.bbox_x or 0)
    y = int(finding.bbox_y or 0)
    w = int(finding.bbox_width or 0)
    h = int(finding.bbox_height or 0)
    if w > 0 and h > 0:
        left = max(0, min(width - 1, x))
        top = max(0, min(height - 1, y))
        right = max(left + 1, min(width, x + w))
        bottom = max(top + 1, min(height, y + h))
        return left, top, right, bottom
    return None


def has_valid_bbox(finding: AnalysisFinding) -> bool:
    return bool((finding.bbox_width or 0) > 0 and (finding.bbox_height or 0) > 0)


def should_annotate_finding(finding: AnalysisFinding) -> bool:
    finding_type = (finding.finding_type or "unknown").lower()
    if has_valid_bbox(finding):
        return finding_type not in NON_ANNOTATED_FINDING_TYPES or bool(finding.confirmed)
    if finding_type in NON_ANNOTATED_FINDING_TYPES:
        return False
    return finding_type in PHYSICAL_FINDING_TYPES and finding.confirmed is not False


def fallback_region(finding: AnalysisFinding, width: int, height: int) -> tuple[int, int, int, int]:
    text = " ".join(str(value or "").lower() for value in [finding.location_label, finding.title, finding.description])
    corner_w = max(1, int(width * 0.28))
    corner_h = max(1, int(height * 0.28))
    edge_w = max(1, int(width * 0.20))
    edge_h = max(1, int(height * 0.18))

    if "top_left" in text or "corner_tl" in text or "bal felső" in text:
        return 0, 0, corner_w, corner_h
    if "top_right" in text or "corner_tr" in text or "jobb felső" in text:
        return width - corner_w, 0, width, corner_h
    if "bottom_left" in text or "corner_bl" in text or "bal alsó" in text:
        return 0, height - corner_h, corner_w, height
    if "bottom_right" in text or "corner_br" in text or "jobb alsó" in text:
        return width - corner_w, height - corner_h, width, height
    if "edge_top" in text or "top edge" in text:
        return 0, 0, width, edge_h
    if "edge_bottom" in text or "bottom edge" in text:
        return 0, height - edge_h, width, height
    if "edge_left" in text or "left edge" in text:
        return 0, 0, edge_w, height
    if "edge_right" in text or "right edge" in text:
        return width - edge_w, 0, width, height
    return int(width * 0.25), int(height * 0.25), int(width * 0.75), int(height * 0.75)


def draw_finding_marker(image: Image.Image, finding: AnalysisFinding, marker_number: int) -> Image.Image:
    annotated = image.convert("RGB")
    draw = ImageDraw.Draw(annotated)
    width, height = annotated.size
    region = bbox_region(finding, width, height) or fallback_region(finding, width, height)
    line_width = max(3, int(min(width, height) * 0.006))
    draw.rectangle(region, outline=(255, 50, 50), width=line_width)

    left, top, _, _ = region
    radius = max(16, int(min(width, height) * 0.025))
    marker_box = (left, top, min(width, left + radius * 2), min(height, top + radius * 2))
    draw.ellipse(marker_box, fill=(255, 50, 50))
    draw.text((left + radius * 0.65, top + radius * 0.35), str(marker_number), fill=(255, 255, 255))
    return annotated


def existing_annotation(session: Session, analysis_run_id: int, finding_id: int) -> AnalysisAsset | None:
    label = f"finding_{finding_id}_annotated"
    return session.exec(
        select(AnalysisAsset)
        .where(AnalysisAsset.analysis_run_id == analysis_run_id)
        .where(AnalysisAsset.asset_type == "annotated_image")
        .where(AnalysisAsset.label == label)
    ).first()


def generate_annotations(session: Session, analysis_run_id: int) -> dict:
    analysis_run = session.get(AnalysisRun, analysis_run_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    findings = session.exec(
        select(AnalysisFinding)
        .where(AnalysisFinding.analysis_run_id == analysis_run_id)
        .order_by(AnalysisFinding.created_at, AnalysisFinding.id)
    ).all()
    if not findings:
        return {"message": "No findings to annotate.", "assets": []}

    output_dir = MEDIA_DIR / "annotated" / str(analysis_run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_assets: list[AnalysisAsset] = []

    for index, finding in enumerate(findings, start=1):
        if finding.id is None:
            continue
        if not should_annotate_finding(finding):
            continue
        existing = existing_annotation(session, analysis_run_id, finding.id)
        if existing is not None and safe_project_path(existing.file_path).is_file():
            created_assets.append(existing)
            continue

        source = choose_source_asset(session, analysis_run, finding)
        if source is None:
            continue
        source_path = safe_project_path(source.file_path)
        if not source_path.is_file():
            continue

        with Image.open(source_path) as image:
            annotated = draw_finding_marker(image, finding, index)
            output_path = output_dir / f"finding_{finding.id}_annotated.jpg"
            annotated.save(output_path, "JPEG", quality=92)

        relative_path = output_path.resolve().relative_to(ROOT.resolve()).as_posix()
        asset = existing or AnalysisAsset(
            analysis_run_id=analysis_run_id,
            asset_type="annotated_image",
            label=f"finding_{finding.id}_annotated",
            file_path=relative_path,
        )
        asset.file_path = relative_path
        session.add(asset)
        session.commit()
        session.refresh(asset)
        created_assets.append(asset)

    return {
        "message": f"Generated {len(created_assets)} annotated assets.",
        "assets": created_assets,
    }
