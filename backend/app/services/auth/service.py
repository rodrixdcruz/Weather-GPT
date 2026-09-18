"""
Dashboard authentication.

Deliberately dependency-free: passwords are hashed with hashlib's PBKDF2
(no passlib/bcrypt needed) and sessions are opaque random tokens stored in
the database. Nothing here ever returns a password or a hash to a caller.

Key product rule: the role is chosen ONCE at login and copied onto the
session row. Every later request that carries the session token resolves
its role from the session, so the UI cannot re-select a role without
logging out.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import Account, LoginSession

log = get_logger(__name__)

_PBKDF2_ROUNDS = 240_000
_SALT_BYTES = 16


def hash_password(password: str, *, salt: str | None = None) -> str:
    """Return `pbkdf2_sha256$rounds$salt$hash` (self-describing, upgradeable)."""
    salt_value = salt or secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt_value}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check against a stored hash. False on any malformed value."""
    try:
        algorithm, rounds, salt_value, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


def get_account_by_username(db: Session, username: str) -> Account | None:
    return db.scalar(select(Account).where(Account.username == username.strip().lower()))


def authenticate(db: Session, username: str, password: str) -> Account | None:
    """Return the account when the credentials are valid and it is active."""
    account = get_account_by_username(db, username)
    if account is None or not account.is_active:
        # Same code path for unknown user and wrong password (no user probing).
        return None
    if not verify_password(password, account.password_hash):
        return None
    return account


def create_session(db: Session, account: Account, role: str) -> LoginSession:
    """Open a session with the role locked in, and record the login time."""
    settings = get_settings()
    now = datetime.utcnow()
    session = LoginSession(
        token=secrets.token_urlsafe(32),
        account_id=account.id,
        role=role,
        created_at=now,
        expires_at=now + timedelta(hours=settings.AUTH_SESSION_TTL_HOURS),
    )
    account.last_login_at = now
    db.add(session)
    db.commit()
    db.refresh(session)
    log.info("auth.login username=%s role=%s admin=%s", account.username, role, account.is_admin)
    return session


def resolve_session(db: Session, token: str | None) -> LoginSession | None:
    """Token → live session, or None when missing/expired/revoked."""
    if not token:
        return None
    session = db.get(LoginSession, token)
    if session is None or session.revoked_at is not None:
        return None
    if session.expires_at <= datetime.utcnow():
        return None
    return session


def revoke_session(db: Session, session: LoginSession) -> None:
    session.revoked_at = datetime.utcnow()
    db.add(session)
    db.commit()
    log.info("auth.logout session_role=%s", session.role)


def is_judge_account(account: Account | None) -> bool:
    """Whether this account is the configured judge/hackathon account.

    Computed from config, never stored: no schema migration, and renaming
    the judge account in config instantly re-points the flag. Single source
    of truth for both the session response and the scenario-simulation gate.
    """
    if account is None:
        return False
    settings = get_settings()
    return bool(
        settings.AUTH_JUDGE_ENABLED
        and account.username == (settings.AUTH_JUDGE_USERNAME or "").strip().lower()
    )


def describe_session(session: LoginSession) -> dict:
    """Serialized shape shared by /auth/* and /admin/* responses."""
    account = session.account
    return {
        "token": session.token,
        "role": session.role,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "user": {
            "username": account.username,
            "display_name": account.display_name or account.username,
            "role": account.role,
            "is_admin": account.is_admin,
            "is_judge": is_judge_account(account),
        },
    }


def list_active_sessions(db: Session) -> list[LoginSession]:
    now = datetime.utcnow()
    return list(
        db.scalars(
            select(LoginSession)
            .where(LoginSession.revoked_at.is_(None), LoginSession.expires_at > now)
            .order_by(LoginSession.created_at.desc())
        )
    )


def seed_accounts(db: Session) -> list[str]:
    """Create the configured admin/demo accounts when they don't exist yet.

    Idempotent: an existing username is left untouched (never resets a
    password someone already changed). Returns the usernames created.

    Only ENABLED accounts are seeded — but note the one-way ratchet: a judge
    account already created in a database stays there after later disabling
    AUTH_JUDGE_ENABLED (seeding never deletes). Deployments that must not have
    one should also drop the row.
    """
    settings = get_settings()
    created: list[str] = []
    seeds = [
        {
            "username": settings.AUTH_ADMIN_USERNAME,
            "password": settings.AUTH_ADMIN_PASSWORD,
            "display_name": settings.AUTH_ADMIN_DISPLAY_NAME,
            "role": "disaster_management_officer",
            "is_admin": True,
        },
        {
            "username": settings.AUTH_DEMO_USERNAME,
            "password": settings.AUTH_DEMO_PASSWORD,
            "display_name": settings.AUTH_DEMO_DISPLAY_NAME,
            "role": "customer",
            "is_admin": False,
        },
    ]
    if settings.AUTH_JUDGE_ENABLED:
        seeds.append(
            {
                "username": settings.AUTH_JUDGE_USERNAME,
                "password": settings.AUTH_JUDGE_PASSWORD,
                "display_name": settings.AUTH_JUDGE_DISPLAY_NAME,
                "role": "customer",
                "is_admin": False,
            }
        )
    for seed in seeds:
        username = (seed["username"] or "").strip().lower()
        if not username or get_account_by_username(db, username):
            continue
        db.add(
            Account(
                username=username,
                password_hash=hash_password(seed["password"]),
                display_name=seed["display_name"],
                role=seed["role"],
                is_admin=seed["is_admin"],
            )
        )
        created.append(username)
    if created:
        db.commit()
        log.info("auth.seeded_accounts %s", created)
    return created
