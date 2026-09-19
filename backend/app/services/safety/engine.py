"""
Safety engine: turns the deterministic risk assessment into a
MausamBagha AI Safety Status, de-duplicated alerts, and a role-aware
checklist. Purely derived from real weather data — never invents alerts,
and never claims official origin (official alerts only come from a
SafetyAlertProvider, if one is ever configured).
"""
from datetime import datetime, timezone

from app.services.risk.engine import RiskEngine
from app.services.risk.models import Severity
from app.services.risk.roles import normalize_role
from app.services.safety.checklists import build_checklist
from app.services.safety.models import SafetyAlert, SafetyStatus
from app.services.safety.providers import get_safety_alert_provider
from app.services.weather.base import ForecastDay, WeatherReading


def _alert_id(category: str, severity: str, latitude: float, longitude: float) -> str:
    """Deterministic id: same risk at the same place = same alert id, so
    the UI/API can de-duplicate across polls."""
    return f"wg_{category}_{severity}_{round(latitude, 2)}_{round(longitude, 2)}"


def alerts_from_risks(assessment) -> list[SafetyAlert]:
    """Convert detected risks into safety alerts (LOW risks stay out —
    an informational risk is not an alert)."""
    alerts: list[SafetyAlert] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    seen: set[str] = set()

    for risk in assessment.risks:
        if risk.severity.rank < Severity.MODERATE.rank:
            continue
        alert = SafetyAlert(
            id=_alert_id(risk.category.value, risk.severity.value, assessment.latitude, assessment.longitude),
            category=risk.category.value,
            severity=risk.severity.value,
            title=risk.title,
            explanation=risk.explanation,
            recommended_action=risk.guidance[0] if risk.guidance else "Monitor official weather updates.",
            timestamp=now_iso,
            latitude=assessment.latitude,
            longitude=assessment.longitude,
            source="weathergpt_risk_engine",
            is_official=False,
        )
        if alert.id not in seen:  # de-duplicate (e.g. current + forecast day overlap)
            seen.add(alert.id)
            alerts.append(alert)

    return alerts


class SafetyEngine:
    """Compose safety status + alerts + checklist from weather + risks."""

    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self._risk_engine = risk_engine or RiskEngine()

    async def assess(
        self,
        reading: WeatherReading,
        forecast: list[ForecastDay] | None = None,
        role: str | None = None,
    ):
        active_role = normalize_role(role)
        risk_assessment = self._risk_engine.assess(reading, forecast=forecast, role=active_role)

        status = SafetyStatus.from_severity(risk_assessment.overall_severity.value)
        alerts = alerts_from_risks(risk_assessment)
        checklist = build_checklist(risk_assessment.risks, active_role)

        # Official alerts only via a real provider; the default returns [].
        official_alerts: list[SafetyAlert] = []
        try:
            provider = get_safety_alert_provider()
            official_alerts = await provider.get_alerts(reading.latitude, reading.longitude)
            # An official alert can escalate the displayed status.
            for alert in official_alerts:
                official_status = SafetyStatus.from_severity(alert.severity)
                if official_status.rank > status.rank:
                    status = official_status
        except Exception as exc:  # noqa: BLE001 - official-feed failure must not break safety
            from app.core.logging import get_logger

            get_logger(__name__).warning("safety.official_provider_failed error=%s", type(exc).__name__)
            official_alerts = []

        from app.services.safety.models import SafetyAssessment

        return SafetyAssessment(
            latitude=risk_assessment.latitude,
            longitude=risk_assessment.longitude,
            role=active_role,
            status=status.value,
            generated_at=datetime.now(timezone.utc).isoformat(),
            weather_source=reading.source,
            weather_is_verified=reading.is_verified,
            observed_at=reading.observed_at,
            condition=reading.condition,
            temperature_c=reading.temperature_c,
            rainfall_mm=reading.rainfall_mm,
            wind_kph=reading.wind_kph,
            humidity_pct=reading.humidity_pct,
            alerts=alerts,
            checklist=[type("ChecklistItem", (), {"text": t, "category": c})() for t, c in checklist],
            official_alerts=official_alerts,
        )
