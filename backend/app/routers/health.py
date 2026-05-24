from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import APP_MODE

router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse({"status": "ok", "mode": APP_MODE})
