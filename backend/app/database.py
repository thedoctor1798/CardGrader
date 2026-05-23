from pathlib import Path
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "cardgrader.db"
DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def init_db():
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    ensure_sqlite_columns()


def ensure_sqlite_columns():
    inspector = inspect(engine)
    if "analysis_findings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("analysis_findings")}
    missing_columns = {
        "side": "TEXT",
        "confirmed": "BOOLEAN",
        "uncertainty_reason": "TEXT",
        "photo_quality_issue": "BOOLEAN",
    }
    with engine.begin() as connection:
        for name, column_type in missing_columns.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE analysis_findings ADD COLUMN {name} {column_type}"))

def get_session():
    with Session(engine) as session:
        yield session
