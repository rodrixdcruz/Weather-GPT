"""Regression tests for DATABASE_URL driver handling (psycopg v3).

Root cause this guards against: SQLAlchemy maps a bare `postgresql://`
URL to its default psycopg2 dialect. This project pins psycopg v3, so a
bare URL (e.g. from an env override) used to crash startup with
`ModuleNotFoundError: No module named 'psycopg2'`.
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.db.session import normalize_database_url


def _driver_for(url: str) -> str:
    """Normalize then create a real engine so the test fails if
    SQLAlchemy's dialect resolution changes."""
    engine = create_engine(normalize_database_url(url))
    return engine.dialect.name, engine.driver


def test_bare_postgresql_url_upgrades_to_psycopg3():
    assert normalize_database_url("postgresql://weathergpt:weathergpt@localhost:5432/weathergpt") == (
        "postgresql+psycopg://weathergpt:weathergpt@localhost:5432/weathergpt"
    )
    name, driver = _driver_for("postgresql://weathergpt:weathergpt@localhost:5432/weathergpt")
    assert name == "postgresql"
    assert driver == "psycopg"  # psycopg v3, NOT psycopg2


def test_explicit_psycopg3_url_is_untouched():
    assert normalize_database_url("postgresql+psycopg://u:p@localhost/db") == "postgresql+psycopg://u:p@localhost/db"
    name, driver = _driver_for("postgresql+psycopg://u:p@localhost/db")
    assert driver == "psycopg"


def test_psycopg2_url_is_left_alone_if_someone_opts_in():
    assert normalize_database_url("postgresql+psycopg2://u:p@localhost/db") == "postgresql+psycopg2://u:p@localhost/db"


def test_config_default_uses_psycopg3():
    from app.core.config import get_settings

    url = make_url(get_settings().DATABASE_URL)
    assert url.drivername == "postgresql+psycopg"


def test_sqlite_url_still_works_for_local_dev():
    name, driver = _driver_for("sqlite:///./dev.db")
    assert name == "sqlite"


def test_app_engine_uses_psycopg3():
    """The engine the app actually creates must be on psycopg v3."""
    from app.db.session import engine

    assert engine.dialect.driver == "psycopg"
