from fastapi import APIRouter, HTTPException, Query

from app.core.logging import get_logger
from app.schemas.schemas import (
    ForecastDayResponse,
    ForecastResponse,
    RiskAssessmentResponse,
    RiskItemResponse,
    RiskResponse,
    WeatherAndRiskResponse,
    WeatherResponse,
)
from app.services.risk.engine import RiskEngine
from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider

router = APIRouter(prefix="/weather", tags=["weather"])
log = get_logger(__name__)


def _weather_response(reading) -> WeatherResponse:
    return WeatherResponse(**reading.__dict__)


def _provider_http_error(exc: WeatherProviderError) -> HTTPException:
    """Map provider failures to clean, user-safe HTTP errors.

    No stack traces or upstream internals reach the client — only the
    pre-sanitized `detail` from the provider.
    """
    status_by_kind = {
        "invalid_coordinates": 422,
        "upstream_unavailable": 503,
        "upstream_error": 502,
        "malformed_response": 502,
    }
    status = status_by_kind.get(exc.kind, 502)
    log.warning("weather.provider_error kind=%s status=%s", exc.kind, status)
    return HTTPException(status_code=status, detail=exc.detail)


async def _fetch_current_reading(latitude: float, longitude: float, scenario: str):
    provider = get_weather_provider(scenario=scenario)
    try:
        return await provider.get_current(latitude, longitude)
    except WeatherProviderError as exc:
        raise _provider_http_error(exc) from None


@router.get("/current", response_model=WeatherAndRiskResponse)
async def get_current_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    scenario: str = Query("normal", description="Demo-only scenario override (mock provider)"),
):
    """Current weather + derived overall risk for a location.

    `is_verified` on the weather payload tells the client whether this
    reading came from an authoritative source or a model estimate —
    the frontend must label it accordingly and never imply certainty
    the data doesn't have.
    """
    reading = await _fetch_current_reading(latitude, longitude, scenario)
    assessment = RiskEngine().assess(reading)

    # Collapse the taxonomy into the legacy single-risk shape: the top
    # priority risk for the default role drives level/hazard/explanation.
    top = assessment.risks[0] if assessment.risks else None
    if top is not None:
        legacy_risk = RiskResponse(
            score=top.score,
            level=top.severity.value,
            hazard_type=top.category.value,
            explanation=f"{top.title}: {top.explanation}",
        )
    else:
        legacy_risk = RiskResponse(
            score=0.0,
            level="low",
            hazard_type=None,
            explanation="No significant weather risks detected for the configured thresholds.",
        )

    log.info("weather.current lat=%.3f lon=%.3f level=%s", latitude, longitude, legacy_risk.level)

    return WeatherAndRiskResponse(weather=_weather_response(reading), risk=legacy_risk)


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    days: int = Query(7, ge=1, le=14),
    scenario: str = Query("normal"),
):
    provider = get_weather_provider(scenario=scenario)
    try:
        forecast = await provider.get_forecast(latitude, longitude, days=days)
    except WeatherProviderError as exc:
        raise _provider_http_error(exc) from None

    log.info("weather.forecast lat=%.3f lon=%.3f days=%s", latitude, longitude, days)
    return ForecastResponse(forecast=[ForecastDayResponse(**f.__dict__) for f in forecast])
