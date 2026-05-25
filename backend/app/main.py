from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import analysis, cards, centering, collection, demo, fx, health, local_ai, media, owned_cards, prices, recognition, settings
from .database import init_db
from .utils.files import ensure_app_dirs
from .config import APP_MODE, CORS_ORIGINS, DATABASE_URL, HOST, LOCAL_AI_ENABLED, MEDIA_DIR, PORT

app = FastAPI(title="CardGrader AI Local Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(centering.router, prefix="/api")
app.include_router(collection.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(fx.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(local_ai.router, prefix="/api")
app.include_router(media.router)
app.include_router(owned_cards.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(recognition.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


@app.get("/")
def root():
    return {
        "app": "CardGrader AI Local Edition",
        "status": "ok",
        "mode": APP_MODE,
        "api_health": "/api/health",
        "frontend": "http://127.0.0.1:5173",
    }


@app.get("/api/app/info")
def app_info():
    return {
        "name": "CardGrader AI Local Edition",
        "mode": APP_MODE,
        "external_apis_enabled": False,
        "local_ai_enabled": LOCAL_AI_ENABLED,
        "database": "sqlite" if DATABASE_URL.startswith("sqlite") else "configured",
        "media_storage": str(MEDIA_DIR),
    }


@app.on_event("startup")
def on_startup():
    ensure_app_dirs()
    init_db()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, log_level="info")
