from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse({"status": "ok", "mode": "local"})
