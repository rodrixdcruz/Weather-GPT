from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.schemas.schemas import ChecklistItemOut, SafetyAlertOut, SafetyAssessmentOut
from app.services.safety.engine import SafetyEngine
from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider

router = APIRouter(prefix="/safety", tags=["safety"])
log = get_logger(__name__)


@router.get("", response_model=SafetyAssessmentOut)
async def get_safety_assessment(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    role: str = Query("customer", description="customer | farmer | traveler | disaster_management_officer"),
    scenario: str = Query("normal", description="Demo-only scenario override (mock provider)"),
):
    """WeatherGPT Safety Status for a location.

    Deterministic: same weather + same profile => same status/alerts.
    `status` is WeatherGPT's own escalation label, NOT an official
    government warning; official alerts only appear if a real
    SafetyAlertProvider is configured (none ships by default).
    """
    provider = get_weather_provider(scenario=scenario)
    try:
        reading = await provider.get_current(latitude, longitude)
    except WeatherProviderError as exc:
        from app.api.v1.routers.weather import _provider_http_error

        log.warning("safety.provider_error kind=%s", exc.kind)
        raise _provider_http_error(exc) from None

    assessment = await SafetyEngine().assess(reading, role=role)

    log.info("safety.assess lat=%.3f lon=%.3f role=%s status=%s alerts=%d", latitude, longitude, assessment.role, assessment.status, len(assessment.alerts))

    return SafetyAssessmentOut(
        latitude=assessment.latitude,
        longitude=assessment.longitude,
        role=assessment.role,
        status=assessment.status,
        generated_at=assessment.generated_at,
        weather_source=assessment.weather_source,
        weather_is_verified=assessment.weather_is_verified,
        observed_at=assessment.observed_at,
        condition=assessment.condition,
        temperature_c=assessment.temperature_c,
        rainfall_mm=assessment.rainfall_mm,
        wind_kph=assessment.wind_kph,
        humidity_pct=assessment.humidity_pct,
        alerts=[SafetyAlertOut(**alert.__dict__) for alert in assessment.alerts],
        checklist=[ChecklistItemOut(text=item.text, category=item.category) for item in assessment.checklist],
        official_alerts=[SafetyAlertOut(**alert.__dict__) for alert in assessment.official_alerts],
        disclaimer=assessment.disclaimer,
    )
