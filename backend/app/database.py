from collections.abc import Generator
import sqlite3

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .core.config import settings


class Base(DeclarativeBase):
    pass


database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(
    database_url,
    connect_args=connect_args,
    future=True,
    pool_pre_ping=True,
)
if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection: sqlite3.Connection, _record: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    if settings.is_production:
        raise RuntimeError("Production schemas must be managed with Alembic migrations.")
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _additive_sqlite_migrations()


def _additive_sqlite_migrations() -> None:
    """Keep existing local SQLite workspaces usable across additive changes."""
    if not settings.database_url.startswith("sqlite"):
        return
    additions: dict[str, dict[str, str]] = {
        "daily_plan_events": {
            "event_name": "VARCHAR(160)",
            "occasion_type": "VARCHAR(100)",
            "budget": "FLOAT",
            "notes": "TEXT",
            "cancelled": "BOOLEAN DEFAULT 0",
        },
        "user_style_preferences": {
            "preferred_sizes": "JSON",
            "preferred_fits": "JSON",
            "shopping_budget": "FLOAT",
        },
        "voice_command_receipts": {
            # Older local databases predate voice language persistence. The
            # default backfills existing receipts and keeps the column valid
            # for new rows when SQLite applies this additive migration.
            "language": "VARCHAR(16) DEFAULT 'en'",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'))
