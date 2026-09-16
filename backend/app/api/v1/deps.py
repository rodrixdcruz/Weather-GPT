"""
Shared request dependencies: who is calling, and are they an admin?

The dashboard sends its session token in the `X-Session-Token` header.
Ordering vs. authentication: `X-Session-Token` is a *custom* header, so the
browser's CORS preflight is required and the server never sets it from a
cookie — no CSRF surface. It is a bearer token: treat it like a password.
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.models import LoginSession
from app.services.auth.service import resolve_session

SESSION_HEADER = "X-Session-Token"


def optional_session(
    db: Session = Depends(get_db),
    x_session_token: str | None = Header(default=None, alias=SESSION_HEADER),
) -> LoginSession | None:
    """The live session for this request, or None when unauthenticated.

    When auth is disabled this always returns None, which keeps every
    endpoint behaving exactly as it did before login existed.
    """
    if not get_settings().AUTH_ENABLED:
        return None
    return resolve_session(db, x_session_token)


def require_session(session: LoginSession | None = Depends(optional_session)) -> LoginSession:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
            headers={"WWW-Authenticate": SESSION_HEADER},
        )
    return session


def require_admin(session: LoginSession = Depends(require_session)) -> LoginSession:
    if not session.account or not session.account.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return session


def effective_role(requested_role: str, session: LoginSession | None) -> str:
    """Resolve the role for a request.

    A signed-in session WINS over whatever the client asked for: the role is
    locked at login, so a caller cannot switch roles by editing a query
    parameter. Without a session (auth disabled, or public/demo use) the
    requested role is honoured, preserving the previous behaviour and tests.
    """
    if session is not None and session.role:
        return session.role
    return requested_role
