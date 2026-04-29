from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from feishu_campus_longmemory.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def ensure_database_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return

    database = url.database
    if not database or database == ":memory:":
        return

    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(settings: Settings) -> Engine:
    ensure_database_parent(settings.database_url)
    return create_engine(
        settings.database_url,
        connect_args=_sqlite_connect_args(settings.database_url),
        future=True,
    )


def run_migrations(settings: Settings) -> None:
    ensure_database_parent(settings.database_url)
    alembic_config = Config(str(ALEMBIC_INI))
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_config, "head")


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

