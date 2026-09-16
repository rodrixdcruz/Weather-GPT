from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.init import init_db

settings = get_settings()
setup_logging()

log = get_logger(__name__)

# Documented development defaults (see backend/.env.example). Named here ONLY so
# that a production start can warn when they are still in use. The values are
# never logged, and nothing is blocked — this is a guard rail, not a gate.
_DEV_DEFAULTS = {
    "AUTH_ADMIN_PASSWORD": "admin123",
    "AUTH_DEMO_PASSWORD": "demo123",
}


def _warn_on_insecure_production_defaults() -> None:
    """Warn when a production deploy still carries development defaults.

    Logs variable NAMES only — never a password, origin list or key.
    """
    if settings.ENV.strip().lower() not in {"production", "prod"}:
        return
    if settings.AUTH_ENABLED:
        for name, dev_value in _DEV_DEFAULTS.items():
            if getattr(settings, name) == dev_value:
                log.warning(
                    "startup.insecure_default variable=%s — set a real value before public use", name
                )
    if settings.CORS_ORIGINS and all(
        "localhost" in origin or "127.0.0.1" in origin for origin in settings.CORS_ORIGINS
    ):
        log.warning(
            "startup.insecure_default variable=CORS_ORIGINS — still localhost-only in production"
        )
    if settings.DOCS_ENABLED:
        log.warning("startup.insecure_default variable=DOCS_ENABLED — API docs are public")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prepare the database (create missing tables, seed accounts).

    Best-effort by design: if Postgres is unavailable the API still starts
    and serves weather/risk — only login is affected, and /admin/overview
    reports the database as unreachable.
    """
    init_db()
    _warn_on_insecure_production_defaults()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    # Interactive docs stay on in development and are switched off in production
    # via DOCS_ENABLED. Route paths, request/response shapes and auth are
    # untouched: only the auto-generated documentation surface changes.
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}
