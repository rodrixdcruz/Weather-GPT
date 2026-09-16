"""
Startup database preparation.

The project previously shipped no migrations at all, so the tables defined
in models/models.py never existed in a fresh database and every write
(sessions, SOS logs) failed quietly. `create_all` is idempotent — it only
creates what is missing — and it is wrapped so a missing database can never
stop the API from serving weather/risk.
"""
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import Base, SessionLocal, engine
from app.models import models  # noqa: F401 - import registers every table

log = get_logger(__name__)


def init_db() -> bool:
    """Create missing tables and seed the configured accounts.

    Returns True when the database was reached. Never raises.
    """
    settings = get_settings()
    if not settings.AUTH_AUTO_INIT_DB:
        return False
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001 - the API must still start
        log.warning("db.init_failed error=%s (weather/risk endpoints stay available)", type(exc).__name__)
        return False

    try:
        from app.services.auth.service import seed_accounts

        with SessionLocal() as db:
            created = seed_accounts(db)
        if created:
            log.info("db.accounts_seeded %s", created)
    except Exception as exc:  # noqa: BLE001 - seeding is best-effort
        log.warning("db.seed_failed error=%s", type(exc).__name__)
    return True
