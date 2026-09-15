"""
Risk engine: the single orchestration point between the weather layer
and the risk layer. Runs the detectors over normalized weather, applies
the role overlay, and returns a RiskAssessment ready for the API layer.

    weather service  ->  risk engine  ->  API  ->  React UI
"""
from datetime import datetime, timezone

from app.services.risk.air_quality_detector import detect_air_quality
from app.services.risk.baseline import NullBaselineProvider, get_baseline_provider, set_baseline_provider
from app.services.risk.detectors import (
    detect_activity_disruption,
    detect_flood_potential,
    detect_forecast_risks,
    detect_heat_stress,
    detect_high_temperature,
    detect_poor_travel_conditions,
    detect_rainfall,
    detect_severe_weather,
    detect_strong_wind,
)
from app.services.risk.models import RiskAssessment, RiskItem
from app.services.risk.profile import RiskProfile, get_risk_profile
from app.services.risk.roles import DEFAULT_ROLE, normalize_role, sort_risks_for_role
from app.services.weather.base import ForecastDay, WeatherReading

# All current-conditions detectors, in taxonomy order. detect_air_quality
# self-silences when the reading carries no air-quality data.
_CURRENT_DETECTORS = (
    detect_rainfall,
    detect_high_temperature,
    detect_heat_stress,
    detect_strong_wind,
    detect_severe_weather,
    detect_flood_potential,
    detect_poor_travel_conditions,
    detect_activity_disruption,
    detect_air_quality,
)


class RiskEngine:
    """Stateless risk-assessment service; safe to share across requests."""

    def __init__(self, profile: RiskProfile | None = None) -> None:
        self._profile = profile or get_risk_profile()
        # Wire the baseline provider once; detectors receive thresholds via
        # the profile, but the provider abstraction stays available for
        # future climatological baselines without touching detectors.
        try:
            get_baseline_provider(self._profile)
        except KeyError:
            set_baseline_provider(NullBaselineProvider(self._profile))

    @property
    def profile_name(self) -> str:
        return self._profile.profile

    def assess(
        self,
        weather: WeatherReading,
        forecast: list[ForecastDay] | None = None,
        role: str | None = None,
    ) -> RiskAssessment:
        """Assess risks for current conditions (+ optional forecast)."""
        active_role = normalize_role(role)
        risks: list[RiskItem] = []
        for detector in _CURRENT_DETECTORS:
            risks.extend(detector(weather, self._profile, active_role))

        if forecast:
            risks.extend(detect_forecast_risks(forecast, self._profile, active_role))

        risks = sort_risks_for_role(risks, self._profile, active_role)

        return RiskAssessment(
            latitude=weather.latitude,
            longitude=weather.longitude,
            role=active_role,
            profile=self._profile.profile,
            assessed_at=datetime.now(timezone.utc).isoformat(),
            weather_source=weather.source,
            weather_is_verified=weather.is_verified,
            observed_at=weather.observed_at,
            condition=weather.condition,
            risks=risks,
        )

    def assess_forecast_only(self, forecast: list[ForecastDay], role: str | None = None) -> list[RiskItem]:
        """Forecast risks without current conditions (used for previews)."""
        active_role = normalize_role(role)
        return sort_risks_for_role(detect_forecast_risks(forecast, self._profile, active_role), self._profile, active_role)

