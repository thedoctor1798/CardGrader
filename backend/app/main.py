from fastapi import FastAPI
from .routers import analysis, cards, collection, demo, health, media, owned_cards, prices
from .database import init_db
from .utils.files import ensure_media_dirs
from .config import HOST, PORT

app = FastAPI(title="CardGrader AI Local Edition")

app.include_router(analysis.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(collection.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(media.router)
app.include_router(owned_cards.router, prefix="/api")
app.include_router(prices.router, prefix="/api")


@app.on_event("startup")
def on_startup():
    init_db()
    ensure_media_dirs()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, log_level="info")
