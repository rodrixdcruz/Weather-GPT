from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import effective_role, optional_session
from app.core.logging import get_logger
from app.models.models import LoginSession
from app.schemas.schemas import (
    RiskAssessmentResponse,
    RiskItemResponse,
    WeatherResponse,
)
from app.services.risk.engine import RiskEngine
from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider, resolve_demo_scenario

router = APIRouter(prefix="/risk", tags=["risk"])
log = get_logger(__name__)


@router.get("", response_model=RiskAssessmentResponse)
async def get_risk_assessment(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    role: str = Query("customer", description="customer | farmer | traveler | disaster_management_officer"),
    scenario: str = Query("normal", description="Judge-demo scenario (ignored for other sessions)"),
    session: LoginSession | None = Depends(optional_session),
):
    """Role-aware weather-risk assessment for a location.

    Reuses the weather service for data (no duplicated provider logic).
    The role changes ordering/emphasis/guidance — never the measurements.
    A signed-in session overrides the `role` parameter: the role is locked
    at login, so it cannot be switched from the dashboard.
    """
    from app.services.risk.roles import normalize_role

    role = effective_role(role, session)
    scenario = resolve_demo_scenario(scenario, session)

    provider = get_weather_provider(scenario=scenario, judge=scenario != "normal")
    try:
        reading = await provider.get_current(latitude, longitude)
    except WeatherProviderError as exc:
        from app.api.v1.routers.weather import _provider_http_error

        log.warning("risk.provider_error kind=%s", exc.kind)
        raise _provider_http_error(exc) from None

    active_role = normalize_role(role)
    assessment = RiskEngine().assess(reading, role=active_role)

    log.info("risk.assess lat=%.3f lon=%.3f role=%s risks=%d", latitude, longitude, active_role, len(assessment.risks))

    return RiskAssessmentResponse(
        latitude=assessment.latitude,
        longitude=assessment.longitude,
        role=assessment.role,
        profile=assessment.profile,
        assessed_at=assessment.assessed_at,
        weather=WeatherResponse(**reading.__dict__),
        condition=assessment.condition,
        overall_severity=assessment.overall_severity.value,
        overall_score=assessment.overall_score,
        risks=[RiskItemResponse(**risk.__dict__) for risk in assessment.risks],
    )
