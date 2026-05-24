from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import analysis, cards, centering, collection, demo, health, local_ai, media, owned_cards, prices
from .database import init_db
from .utils.files import ensure_media_dirs
from .config import HOST, LOCAL_AI_ENABLED, PORT

app = FastAPI(title="CardGrader AI Local Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8710",
        "http://localhost:8710",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(centering.router, prefix="/api")
app.include_router(collection.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(local_ai.router, prefix="/api")
app.include_router(media.router)
app.include_router(owned_cards.router, prefix="/api")
app.include_router(prices.router, prefix="/api")


@app.get("/")
def root():
    return {
        "app": "CardGrader AI Local Edition",
        "status": "ok",
        "mode": "local-only",
        "api_health": "/api/health",
        "frontend": "http://127.0.0.1:5173",
    }


@app.get("/api/app/info")
def app_info():
    return {
        "name": "CardGrader AI Local Edition",
        "mode": "local-only",
        "external_apis_enabled": False,
        "local_ai_enabled": LOCAL_AI_ENABLED,
        "database": "sqlite",
        "media_storage": "local",
    }


@app.on_event("startup")
def on_startup():
    init_db()
    ensure_media_dirs()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, log_level="info")
