from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "cardgrader.db"
DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
