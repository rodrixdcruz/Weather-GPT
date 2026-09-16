"""
Core persistence models.

Kept intentionally small for the MVP: locations users care about, alerts
issued for those locations, chat history for the conversational layer,
and SOS events (logging only — see services/sos.py for why we never
fake a dispatch confirmation).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Account(Base):
    """A dashboard login.

    `role` is the role CHOSEN AT LOGIN and is copied onto each LoginSession:
    the role is locked for the lifetime of that session (the UI cannot switch
    it — the user must log out to pick a different one). `is_admin` unlocks
    the admin panel.
    """

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="customer")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["LoginSession"]] = relationship(back_populates="account")


class LoginSession(Base):
    """An authenticated dashboard session. `role` is frozen at login time."""

    __tablename__ = "login_sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="sessions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    phone: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    saved_locations: Mapped[list["SavedLocation"]] = relationship(back_populates="user")
    sos_events: Mapped[list["SosEvent"]] = relationship(back_populates="user")


class SavedLocation(Base):
    __tablename__ = "saved_locations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    label: Mapped[str] = mapped_column(String)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="saved_locations")


class WeatherAlert(Base):
    """A risk/hazard alert generated for a location + time window.

    `is_verified` tracks whether this came from an authoritative source
    (e.g. IMD/NDMA feed) vs. a model-derived estimate — this MUST be
    surfaced in the UI per the "never invent verified data" requirement.
    """

    __tablename__ = "weather_alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    hazard_type: Mapped[str] = mapped_column(String)  # e.g. heavy_rainfall, heatwave
    risk_level: Mapped[str] = mapped_column(String)  # low | moderate | high | critical
    risk_score: Mapped[int] = mapped_column(Float)
    headline: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String)  # e.g. "IMD", "model_estimate"
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String, default="en")
    data_used: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot of weather/risk used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SosEvent(Base):
    """Logs an SOS trigger. NEVER mark `dispatched=True` unless a real
    dispatch integration confirmed delivery — see services/sos.py.
    """

    __tablename__ = "sos_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatch_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="sos_events")


class SafetyEvent(Base):
    """Lightweight history of detected safety events (Phase 4).

    Privacy: stores only the event itself — event type, severity,
    rounded coordinates, timestamp and status. No user identifiers,
    no addresses, no personal data. Rounded coords (~1km grid) keep this
    useful for aggregates without tracking individuals.
    """

    __tablename__ = "safety_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String)  # risk category, e.g. rainfall
    severity: Mapped[str] = mapped_column(String)  # low | moderate | high | extreme
    latitude: Mapped[float] = mapped_column(Float)  # rounded to ~2 decimals (~1km)
    longitude: Mapped[float] = mapped_column(Float)  # rounded to ~2 decimals (~1km)
    status: Mapped[str] = mapped_column(String)  # WeatherGPT safety status at detection
    source: Mapped[str] = mapped_column(String)  # always "weathergpt_risk_engine" for now
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
