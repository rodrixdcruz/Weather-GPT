"""
Air-quality risk detector. Runs only when REAL air-quality data is
attached to the reading (Open-Meteo AQI enrichment or the mock fixture) —
a reading without air quality means "no data", and the detector stays
silent rather than guessing.

Thresholds come from the risk profile's `us_aqi` bands (US EPA breakpoints
converted to WeatherGPT risk severities; India's CPCB national AQI uses
different scales, so the profile remains adjustable per region).
"""
from app.services.risk.guidance import guidance_for
from app.services.risk.models import RiskCategory, RiskItem, Severity
from app.services.risk.profile import RiskProfile
from app.services.weather.base import WeatherReading


def detect_air_quality(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Flag poor air quality when a verified AQI value is present."""
    aqi = weather.air_quality
    if aqi is None:
        return []  # no enrichment -> no fabricated claims

    thresholds = profile.thresholds.us_aqi
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    value = aqi.us_aqi
    if value < bands["moderate"]:
        return []

    severity = _band(value, bands)
    band_label = aqi.band or f"AQI {value:.0f}"
    return [
        RiskItem(
            category=RiskCategory.AIR_QUALITY,
            severity=severity,
            score=_score_from_severity(severity, value, bands),
            title=_title(RiskCategory.AIR_QUALITY),
            explanation=(
                f"Air quality is {band_label} (US AQI about {value:.0f}), above the {severity.value} "
                f"air-quality threshold of {bands[severity.value]:.0f}. Sensitive groups should take precautions first."
            ),
            guidance=[guidance_for(profile, RiskCategory.AIR_QUALITY, role)],
            affected_metric="us_aqi",
            measured_value=value,
        )
    ]


def _band(measured: float, thresholds: dict[str, float]) -> Severity:
    if measured >= thresholds["extreme"]:
        return Severity.EXTREME
    if measured >= thresholds["high"]:
        return Severity.HIGH
    if measured >= thresholds["moderate"]:
        return Severity.MODERATE
    return Severity.LOW


def _score_from_severity(severity: Severity, measured: float, thresholds: dict[str, float]) -> float:
    """Same explainable 0-100 scoring as the other detectors (band base +
    depth into band); imported lazily to avoid duplicating the formula."""
    from app.services.risk.detectors import _score_from_severity as shared

    return shared(severity, measured, thresholds)


def _title(category: RiskCategory) -> str:
    return category.value.replace("_", " ").title()
