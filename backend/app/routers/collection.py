from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..schemas import CollectionSnapshotRead, CollectionSummaryRead, CollectionValuationRead
from ..services.pricing import (
    calculate_collection_summary,
    create_collection_snapshot,
    list_collection_snapshots,
)
from ..services.valuation_service import calculate_collection_valuation

router = APIRouter()


@router.post("/collection/snapshot", response_model=CollectionSnapshotRead, status_code=201)
def create_snapshot(session: Session = Depends(get_session)):
    return create_collection_snapshot(session)


@router.get("/collection/snapshots", response_model=List[CollectionSnapshotRead])
def get_snapshots(session: Session = Depends(get_session)):
    return list_collection_snapshots(session)


@router.get("/collection/summary", response_model=CollectionSummaryRead)
def get_collection_summary(session: Session = Depends(get_session)):
    return calculate_collection_summary(session)


@router.get("/collection/valuation", response_model=CollectionValuationRead)
def get_collection_valuation(session: Session = Depends(get_session)):
    return calculate_collection_valuation(session)
