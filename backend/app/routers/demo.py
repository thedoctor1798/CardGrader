from pathlib import Path

from fastapi import APIRouter, Depends
from sqlmodel import Session, delete, func, select

from ..config import MEDIA_DIR
from ..database import get_session
from ..models import (
    AnalysisAsset,
    AnalysisFinding,
    AnalysisRun,
    Card,
    CardMedia,
    CollectionSnapshot,
    OwnedCard,
    PriceObservation,
)

router = APIRouter()


@router.post("/demo/seed-rowlet", status_code=201)
def seed_rowlet(session: Session = Depends(get_session)):
    card_statement = (
        select(Card)
        .where(Card.name == "Rowlet")
        .where(Card.set_name == "ME03: Perfect Order")
        .where(Card.set_code == "POR")
        .where(Card.card_number == "090/088")
        .order_by(Card.id)
    )
    matching_cards = session.exec(card_statement).all()
    card = matching_cards[0] if matching_cards else None
    created_card = False
    if card is None:
        card = Card(
            name="Rowlet",
            set_name="ME03: Perfect Order",
            set_code="POR",
            card_number="090/088",
        )
        session.add(card)
        session.commit()
        session.refresh(card)
        created_card = True

    card_ids = [item.id for item in matching_cards if item.id is not None]
    if card.id not in card_ids:
        card_ids.append(card.id)

    owned_card = None
    if card_ids:
        owned_card_statement = (
            select(OwnedCard)
            .where(OwnedCard.card_id.in_(card_ids))
            .where(OwnedCard.copy_label == "Rowlet demo copy")
            .order_by(OwnedCard.id)
        )
        owned_card = session.exec(owned_card_statement).first()
        if owned_card is not None and owned_card.card_id != card.id:
            existing_card = session.get(Card, owned_card.card_id)
            if existing_card is not None:
                card = existing_card

    created_owned_card = False
    if owned_card is None:
        owned_card = OwnedCard(
            card_id=card.id,
            copy_label="Rowlet demo copy",
            status="raw_owned",
            acquired_source="unknown",
        )
        session.add(owned_card)
        session.commit()
        session.refresh(owned_card)
        created_owned_card = True

    if created_card or created_owned_card:
        message = "Rowlet demo seed completed."
    else:
        message = "Rowlet demo already exists."

    return {
        "card": card,
        "owned_card": owned_card,
        "created_card": created_card,
        "created_owned_card": created_owned_card,
        "created": created_card or created_owned_card,
        "message": message,
    }


def delete_all_rows(session: Session, model) -> int:
    count = session.exec(select(func.count()).select_from(model)).one()
    session.exec(delete(model))
    return int(count)


@router.post("/demo/reset-local-data")
def reset_local_data(session: Session = Depends(get_session)):
    deleted = {
        "analysis_assets": delete_all_rows(session, AnalysisAsset),
        "analysis_findings": delete_all_rows(session, AnalysisFinding),
        "analysis_runs": delete_all_rows(session, AnalysisRun),
        "card_media": delete_all_rows(session, CardMedia),
        "price_observations": delete_all_rows(session, PriceObservation),
        "collection_snapshots": delete_all_rows(session, CollectionSnapshot),
        "owned_cards": delete_all_rows(session, OwnedCard),
        "cards": delete_all_rows(session, Card),
    }
    session.commit()
    return {
        "status": "ok",
        "message": "Local demo data reset completed.",
        "deleted": deleted,
    }


def cleanup_folder(folder: Path) -> int:
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return 0

    deleted_files = 0
    for path in sorted(folder.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
            deleted_files += 1
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    folder.mkdir(parents=True, exist_ok=True)
    return deleted_files


@router.post("/demo/cleanup-generated-media")
def cleanup_generated_media():
    folders = ["resized", "normalized", "crops", "annotated", "video_frames", "reports"]
    deleted = {folder: cleanup_folder(MEDIA_DIR / folder) for folder in folders}
    return {
        "status": "ok",
        "message": "Generated media cleanup completed.",
        "deleted_files": sum(deleted.values()),
        "deleted": deleted,
    }
