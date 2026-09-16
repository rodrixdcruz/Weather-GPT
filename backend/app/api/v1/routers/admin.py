"""
Admin panel API (admin accounts only).

WeatherGPT's intelligence is a MODEL STACK, so the panel is built around
model observability rather than generic server stats:

  1. Which model tiers are configured and actually reachable
     (local Ollama → Solar Pro 4 escalation → deterministic data fallback).
  2. What the model has been doing since start: requests, which tier served
     them, fallback rate, latency distribution.
  3. The deterministic layer around it (risk engine profile, safety
     provider, data sources) so admins can see what the model is grounded in.
  4. Who is signed in, and with which locked role.

No secret is ever returned: API keys are reported as booleans only.
"""
import platform
import sys
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.models import Account, LoginSession
from app.services.ai.factory import get_ai_provider
from app.services.ai.metrics import get_metrics
from app.services.risk.profile import get_risk_profile
from app.services.risk.roles import KNOWN_ROLES

router = APIRouter(prefix="/admin", tags=["admin"])

_STARTED_AT = time.time()


def _tier(name: str, model: str, configured: bool, detail: str, **extra) -> dict:
    return {"name": name, "model": model, "configured": configured, "detail": detail, **extra}


async def _model_tiers(settings) -> list[dict]:
    """Describe the model chain and probe the local tier's reachability.

    Only the local Ollama tier is probed live (cheap, local, no spend).
    Solar is reported as configured/not-configured: probing it would cost
    money on every panel refresh.
    """
    tiers: list[dict] = []
    provider = (settings.AI_PROVIDER or "mock").lower()

    if provider == "mock":
        return [
            _tier(
                "deterministic-mock",
                settings.AI_MODEL or "mock",
                True,
                "AI_PROVIDER=mock — template answers, no model call. Set AI_PROVIDER=hybrid for real inference.",
            )
        ]
    if provider == "openai":
        return [
            _tier(
                "openai",
                settings.AI_MODEL or "gpt-4o-mini",
                bool(settings.AI_API_KEY),
                "Cloud model. API key configured." if settings.AI_API_KEY else "AI_API_KEY is not set.",
            )
        ]

    # ollama and hybrid both expose a local tier; hybrid adds Solar escalation.
    reachable = False
    detail = "Not reachable."
    try:
        from app.services.ai.ollama_provider import OllamaProvider

        ollama = OllamaProvider()
        reachable = await ollama.is_available()
        detail = "Local model responding." if reachable else f"No response from {settings.OLLAMA_BASE_URL}."
    except Exception as exc:  # noqa: BLE001 - a probe failure must not 500 the panel
        detail = f"Probe failed ({type(exc).__name__})."
    tiers.append(_tier("ollama (local)", settings.OLLAMA_MODEL, reachable, detail))

    if provider == "hybrid":
        tiers.append(_escalation_tier(settings))
    return tiers


def _escalation_tier(settings, provider=None) -> dict:
    """Describe the FREE escalation chain the hybrid provider will use.

    Every chain member gets its own report card (preset name, model, free
    limits, key status, cooldown state), so an operator can see exactly which
    free services are wired in, in which order, and how to replace them — a
    stale preset or an exhausted tier is then visible rather than mysterious.
    """
    from app.services.ai.factory import get_ai_provider
    from app.services.ai.presets import preset_names

    hybrid = provider or get_ai_provider()
    members = []
    active: set[str] | None = None
    if hasattr(hybrid, "escalation_members"):
        members = hybrid.escalation_members
        active = set(hybrid.escalation_active_names())
    else:
        try:
            from app.services.ai.cloud_provider import CloudChatProvider

            members = [CloudChatProvider()]
        except ValueError as exc:
            return _tier(
                "escalation (cloud)",
                settings.ESCALATION_PROVIDER,
                False,
                f"{exc} Valid options: {', '.join(preset_names())}.",
            )

    if not members:
        return _tier("escalation (cloud)", settings.ESCALATION_PROVIDER, False, "No escalation provider resolved.")

    reports = []
    for member in members:
        preset = member.preset
        configured = member.has_credentials or not preset.requires_key
        cooling = active is not None and preset.name not in active
        if configured and not cooling:
            detail = "Free tier — used only when the local model fails or a question needs broader knowledge."
        elif cooling:
            detail = f"Rate-limited recently — skipped for {int(settings.ESCALATION_COOLDOWN_SECONDS)}s (failover to the next tier handles requests meanwhile)."
        else:
            detail = (
                f"No key set, so this tier is dormant. Get a free key at {preset.signup_url}, "
                f"or use the keyless 'ovhcloud' tier."
            )
        reports.append({
            **_tier(
                preset.label,
                member.model,
                configured and not cooling,
                detail,
                base_url=member.base_url,
                limits=preset.limits,
                requires_key=preset.requires_key,
                signup_url=preset.signup_url,
                preset=preset.name,
                free=preset.name != "solar",
            ),
            "cooling": cooling,
        })

    order = " → ".join(r["preset"] for r in reports)
    return _tier(
        f"escalation chain: {order}" if len(reports) > 1 else f"{reports[0]['name']} (escalation)",
        reports[0]["model"],
        any(r["configured"] for r in reports),
        (
            f"Ordered failover over {len(reports)} free providers — a rate limit or outage on one is absorbed by the next. "
            f"Primary: {reports[0]['name']}."
            if len(reports) > 1 else reports[0]["detail"]
        ),
        members=reports,
        limits=" · ".join(r["limits"] for r in reports) or None,
    )

    preset = provider.preset
    configured = provider.has_credentials or not preset.requires_key
    if configured:
        detail = (
            f"Active free tier — used only when the local model fails or a question needs broader "
            f"knowledge. Free limits: {preset.limits}."
        )
    else:
        detail = (
            f"No key set, so this tier is dormant. Get a free key at {preset.signup_url}, "
            f"or set ESCALATION_PROVIDER=ovhcloud to use a keyless free tier."
        )

    return _tier(
        f"{preset.label} (escalation)",
        provider.model,
        configured,
        detail,
        base_url=provider.base_url,
        limits=preset.limits,
        requires_key=preset.requires_key,
        signup_url=preset.signup_url,
        preset=preset.name,
        free=preset.name != "solar",
    )


@router.get("/overview")
async def overview(
    _admin: LoginSession = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Model + system snapshot for the admin panel."""
    settings = get_settings()
    metrics = get_metrics().snapshot()
    notes: list[str] = []

    risk_engine: dict = {
        "profile": settings.RISK_PROFILE,
        "roles": list(KNOWN_ROLES),
        "thresholds": None,
        "severities": None,
    }
    try:
        profile = get_risk_profile()
        risk_engine.update(
            {
                "profile": profile.profile,
                "description": profile.description,
                "severities": list(profile.severities),
                "thresholds": profile.thresholds.model_dump(),
                "role_priorities": {role: len(cats) for role, cats in profile.role_priorities.items()},
                "guidance_templates": len(profile.guidance_templates),
            }
        )
    except Exception as exc:  # noqa: BLE001 - report the problem, never 500 the panel
        notes.append(f"Risk profile '{settings.RISK_PROFILE}' could not be loaded ({type(exc).__name__}).")

    database_ok = True
    counts = {"accounts": 0, "active_sessions": 0}
    try:
        counts["accounts"] = db.scalar(select(func.count()).select_from(Account)) or 0
        counts["active_sessions"] = db.scalar(
            select(func.count())
            .select_from(LoginSession)
            .where(LoginSession.revoked_at.is_(None), LoginSession.expires_at > datetime.utcnow())
        ) or 0
    except Exception:  # noqa: BLE001 - DB down must not break the panel
        database_ok = False
        notes.append("Database unreachable — session persistence is degraded.")

    return {
        "app": {
            "name": settings.APP_NAME,
            "version": "0.1.0",
            "env": settings.ENV,
            "uptime_seconds": int(time.time() - _STARTED_AT),
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "runtime": sys.implementation.name,
        },
        "model": {
            "provider_mode": settings.AI_PROVIDER,
            "tiers": await _model_tiers(settings),
            "rag": {
                "enabled": settings.RAG_ENABLED,
                "top_k": settings.RAG_TOP_K,
                "source": settings.RAG_KNOWLEDGE_DIR or "built-in knowledge base",
            },
            "metrics": metrics,
        },
        "deterministic_layer": {
            "risk_engine": risk_engine,
            "safety_alert_provider": settings.SAFETY_ALERT_PROVIDER,
            "data_sources": {
                "weather_provider": settings.WEATHER_PROVIDER,
                "air_quality_enabled": settings.AIR_QUALITY_ENABLED,
                "sos_dispatch_enabled": settings.SOS_DISPATCH_ENABLED,
            },
        },
        "database": {"reachable": database_ok, **counts},
        "auth": {
            "enabled": settings.AUTH_ENABLED,
            "session_ttl_hours": settings.AUTH_SESSION_TTL_HOURS,
        },
        "notes": notes,
    }


@router.get("/sessions")
def sessions(
    _admin: LoginSession = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Active sessions — each one carrying its own locked role."""
    from app.services.auth.service import list_active_sessions

    rows = []
    for session in list_active_sessions(db):
        account = session.account
        rows.append(
            {
                "username": account.username if account else "(deleted account)",
                "display_name": (account.display_name or account.username) if account else "-",
                "is_admin": bool(account.is_admin) if account else False,
                "session_role": session.role,
                "account_role": account.role if account else "-",
                "role_locked": bool(account and session.role != account.role),
                "created_at": session.created_at,
                "expires_at": session.expires_at,
            }
        )
    return {"count": len(rows), "sessions": rows}
