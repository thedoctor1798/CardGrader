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
    tables = set(inspector.get_table_names())
    table_columns = {
        "analysis_findings": {
            "side": "TEXT",
            "confirmed": "BOOLEAN",
            "uncertainty_reason": "TEXT",
            "photo_quality_issue": "BOOLEAN",
        },
        "card_media": {
            "derived_from_media_id": "INTEGER",
            "edit_type": "TEXT",
            "edit_metadata": "TEXT",
        },
        "centering_measurements": {
            "outer_left_pct": "REAL",
            "outer_right_pct": "REAL",
            "outer_top_pct": "REAL",
            "outer_bottom_pct": "REAL",
            "inner_left_pct": "REAL",
            "inner_right_pct": "REAL",
            "inner_top_pct": "REAL",
            "inner_bottom_pct": "REAL",
        },
    }
    with engine.begin() as connection:
        for table_name, missing_columns in table_columns.items():
            if table_name not in tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for name, column_type in missing_columns.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}"))

def get_session():
    with Session(engine) as session:
        yield session
