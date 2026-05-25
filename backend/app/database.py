from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from .config import DATABASE_URL, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

def init_db():
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    ensure_sqlite_columns()
    ensure_sqlite_card_media_owned_card_nullable()


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
        "analysis_runs": {
            "image_labels_json": "TEXT",
            "allowed_areas_json": "TEXT",
            "warnings_json": "TEXT",
            "model_parameters_json": "TEXT",
            "analysis_scope": "TEXT",
            "image_payload_json": "TEXT",
        },
        "fx_rates": {
            "error_code": "TEXT",
            "error_message": "TEXT",
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


def ensure_sqlite_card_media_owned_card_nullable():
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "card_media" not in set(inspector.get_table_names()):
        return

    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(card_media)")).mappings().all()
        owned_column = next((column for column in columns if column["name"] == "owned_card_id"), None)
        if owned_column is None or int(owned_column["notnull"]) == 0:
            return

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE card_media_new (
                    id INTEGER PRIMARY KEY,
                    owned_card_id INTEGER,
                    media_type TEXT,
                    label TEXT,
                    file_path TEXT NOT NULL,
                    original_filename TEXT,
                    width INTEGER,
                    height INTEGER,
                    file_size_bytes INTEGER,
                    derived_from_media_id INTEGER,
                    edit_type TEXT,
                    edit_metadata TEXT,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(owned_card_id) REFERENCES owned_cards (id),
                    FOREIGN KEY(derived_from_media_id) REFERENCES card_media (id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO card_media_new (
                    id,
                    owned_card_id,
                    media_type,
                    label,
                    file_path,
                    original_filename,
                    width,
                    height,
                    file_size_bytes,
                    derived_from_media_id,
                    edit_type,
                    edit_metadata,
                    created_at
                )
                SELECT
                    id,
                    owned_card_id,
                    media_type,
                    label,
                    file_path,
                    original_filename,
                    width,
                    height,
                    file_size_bytes,
                    derived_from_media_id,
                    edit_type,
                    edit_metadata,
                    created_at
                FROM card_media
                """
            )
        )
        connection.execute(text("DROP TABLE card_media"))
        connection.execute(text("ALTER TABLE card_media_new RENAME TO card_media"))
        connection.execute(text("PRAGMA foreign_keys=ON"))

def get_session():
    with Session(engine) as session:
        yield session
