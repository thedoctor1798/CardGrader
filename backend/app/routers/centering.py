from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import CenteringMeasurement, OwnedCard
from ..schemas.centering import CenteringMeasurementCreate, CenteringMeasurementRead
from ..services.centering import create_centering_measurement, latest_manual_centering

router = APIRouter()


@router.post("/owned-cards/{owned_card_id}/centering-measurements", response_model=CenteringMeasurementRead, status_code=201)
def post_centering_measurement(
    owned_card_id: int,
    payload: CenteringMeasurementCreate,
    session: Session = Depends(get_session),
):
    return create_centering_measurement(session, owned_card_id, payload)


@router.get("/owned-cards/{owned_card_id}/centering-measurements", response_model=List[CenteringMeasurementRead])
def list_centering_measurements(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    return session.exec(
        select(CenteringMeasurement)
        .where(CenteringMeasurement.owned_card_id == owned_card_id)
        .order_by(CenteringMeasurement.created_at.desc(), CenteringMeasurement.id.desc())
    ).all()


@router.get("/owned-cards/{owned_card_id}/latest-centering", response_model=CenteringMeasurementRead)
def get_latest_centering(
    owned_card_id: int,
    session: Session = Depends(get_session),
):
    if session.get(OwnedCard, owned_card_id) is None:
        raise HTTPException(status_code=404, detail="Owned card not found")
    measurement = latest_manual_centering(session, owned_card_id)
    if measurement is None:
        raise HTTPException(status_code=404, detail="No manual centering measurement exists for this owned card.")
    return measurement
