from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.deps import SESSION_HEADER, require_session
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.models import LoginSession
from app.schemas.schemas import LoginRequest, SessionResponse
from app.services.auth.service import (
    authenticate,
    create_session,
    describe_session,
    revoke_session,
)
from app.services.risk.roles import normalize_role

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Sign in and LOCK IN the chosen role for this session.

    The role is selected here, once. The dashboard has no role switcher, and
    the backend resolves roles from this session — so changing it requires
    logging out.
    """
    if not get_settings().AUTH_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authentication is disabled.")

    account = authenticate(db, payload.username, payload.password)
    if account is None:
        log.info("auth.login_rejected username=%s", payload.username)
        # One message for both "no such user" and "wrong password".
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

    role = normalize_role(payload.role) if payload.role else account.role
    session = create_session(db, account, role)
    return SessionResponse(**describe_session(session))


@router.get("/session", response_model=SessionResponse)
def current_session(session: LoginSession = Depends(require_session)):
    """Who am I, and which role is locked in for this session."""
    return SessionResponse(**describe_session(session))


@router.post("/logout", response_model=dict)
def logout(session: LoginSession = Depends(require_session), db: Session = Depends(get_db)):
    """Revoke this session. The role lock lives and dies with the session."""
    revoke_session(db, session)
    return {"ok": True, "message": "Signed out."}


# Re-exported so the frontend and tests read the header name from one place.
__all__ = ["router", "SESSION_HEADER"]
