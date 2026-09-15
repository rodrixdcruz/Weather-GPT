"""
Detectors turn one normalized weather snapshot into concrete risks.
Every detector follows the same contract:

    detect(weather, profile, guidance_fn) -> list[RiskItem]

They receive the canonical WeatherReading / ForecastDay models only —
never a provider payload — and read every threshold from the profile.
Wind inputs are kph (the canonical unit for WeatherReading.wind_kph).
"""
from app.services.risk.guidance import guidance_for
from app.services.risk.models import RiskCategory, RiskItem, Severity
from app.services.risk.profile import RiskProfile
from app.services.weather.base import ForecastDay, WeatherReading


def _band(measured: float, thresholds: dict[str, float]) -> Severity:
    """Map a measurement to a severity band given ascending thresholds."""
    if measured >= thresholds["extreme"]:
        return Severity.EXTREME
    if measured >= thresholds["high"]:
        return Severity.HIGH
    if measured >= thresholds["moderate"]:
        return Severity.MODERATE
    return Severity.LOW


def _score_from_severity(severity: Severity, measured: float, thresholds: dict[str, float]) -> float:
    """Convert severity band + how deep into the band into a 0-100 score.

    Scores stay proportional and explainable: a value just over a
    threshold scores just above that band's base, never wildly higher.
    Band bases: low=0-20, moderate=20-45, high=45-75, extreme=75-100.
    """
    rank = severity.rank
    if rank == 0:
        return round(min(19.9, max(0.0, measured / max(thresholds["moderate"], 0.0001) * 19.9)), 1)
    lower = thresholds[severity.value]
    upper = thresholds["extreme"] if rank == 3 else thresholds[Severity.from_rank(rank + 1).value]
    band_width = max(upper - lower, 0.0001)
    depth = max(0.0, min(1.0, (measured - lower) / band_width))
    base = {1: 20.0, 2: 45.0, 3: 75.0}[rank]
    top = {1: 45.0, 2: 75.0, 3: 100.0}[rank]
    return round(min(100.0, base + depth * (top - base)), 1)


def _title(category: RiskCategory) -> str:
    return category.value.replace("_", " ").title()


def _detection_context(weather: WeatherReading) -> dict[str, object]:
    """Aggregate context across current conditions (shared by composite detectors)."""
    rainfall_max = weather.rainfall_mm
    wind_max = weather.wind_kph
    gust = weather.wind_gust_kph
    if gust is not None:
        wind_max = max(wind_max, gust)
    code = weather.weather_code
    return {"rainfall_max": rainfall_max, "wind_max": wind_max, "code": code}


def detect_rainfall(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    thresholds = profile.thresholds.rainfall_mm_per_day
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    rainfall = weather.rainfall_mm
    if rainfall < bands["moderate"]:
        return []
    severity = _band(rainfall, bands)
    return [
        RiskItem(
            category=RiskCategory.RAINFALL,
            severity=severity,
            score=_score_from_severity(severity, rainfall, bands),
            title=_title(RiskCategory.RAINFALL),
            explanation=f"Rainfall is around {rainfall:.0f} mm for the day, above the {severity.value} risk threshold of {bands[severity.value]:.1f} mm.",
            guidance=[guidance_for(profile, RiskCategory.RAINFALL, role)],
            affected_metric="rainfall_mm_per_day",
            measured_value=rainfall,
        )
    ]


def detect_high_temperature(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    thresholds = profile.thresholds.temperature_c
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    temperature = weather.temperature_c
    if temperature < bands["moderate"]:
        return []
    severity = _band(temperature, bands)
    return [
        RiskItem(
            category=RiskCategory.HIGH_TEMPERATURE,
            severity=severity,
            score=_score_from_severity(severity, temperature, bands),
            title=_title(RiskCategory.HIGH_TEMPERATURE),
            explanation=f"Temperature is around {temperature:.0f}°C, above the {severity.value} heat threshold of {bands[severity.value]:.0f}°C.",
            guidance=[guidance_for(profile, RiskCategory.HIGH_TEMPERATURE, role)],
            affected_metric="temperature_c",
            measured_value=temperature,
        )
    ]


def detect_heat_stress(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Heat stress uses apparent temperature when available (what the body
    actually feels, factoring humidity + wind); it falls back to air
    temperature when the provider doesn't supply it."""
    thresholds = profile.thresholds.apparent_temperature_c
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    feels_like = weather.apparent_temperature_c if weather.apparent_temperature_c is not None else weather.temperature_c
    if feels_like < bands["moderate"]:
        return []
    severity = _band(feels_like, bands)
    metric = "apparent_temperature_c" if weather.apparent_temperature_c is not None else "temperature_c"
    label = "Feels-like" if metric == "apparent_temperature_c" else "Air temperature"
    return [
        RiskItem(
            category=RiskCategory.HEAT_STRESS,
            severity=severity,
            score=_score_from_severity(severity, feels_like, bands),
            title=_title(RiskCategory.HEAT_STRESS),
            explanation=f"{label} is around {feels_like:.0f}°C, above the {severity.value} heat-stress threshold of {bands[severity.value]:.0f}°C.",
            guidance=[guidance_for(profile, RiskCategory.HEAT_STRESS, role)],
            affected_metric=metric,
            measured_value=feels_like,
        )
    ]


def detect_strong_wind(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Strong wind uses the stronger of sustained wind and gusts."""
    thresholds = profile.thresholds.wind_kph
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    wind = weather.wind_gust_kph if weather.wind_gust_kph is not None and weather.wind_gust_kph > weather.wind_kph else weather.wind_kph
    if wind < bands["moderate"]:
        return []
    severity = _band(wind, bands)
    metric = "wind_gust_kph" if weather.wind_gust_kph is not None and weather.wind_gust_kph > weather.wind_kph else "wind_kph"
    label = "Wind gusts" if metric == "wind_gust_kph" else "Sustained wind"
    return [
        RiskItem(
            category=RiskCategory.STRONG_WIND,
            severity=severity,
            score=_score_from_severity(severity, wind, bands),
            title=_title(RiskCategory.STRONG_WIND),
            explanation=f"{label} reach about {wind:.0f} km/h, above the {severity.value} wind threshold of {bands[severity.value]:.0f} km/h.",
            guidance=[guidance_for(profile, RiskCategory.STRONG_WIND, role)],
            affected_metric=metric,
            measured_value=wind,
        )
    ]


def detect_severe_weather(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Severe weather flags thunderstorm-class WMO codes from the profile."""
    codes = set(profile.thresholds.severe_weather_codes)
    code = weather.weather_code
    if code is None or code not in codes:
        return []
    severity = Severity.EXTREME if code in (96, 99) else Severity.HIGH
    score = {Severity.HIGH: 60.0, Severity.EXTREME: 85.0}[severity]
    return [
        RiskItem(
            category=RiskCategory.SEVERE_WEATHER,
            severity=severity,
            score=score,
            title=_title(RiskCategory.SEVERE_WEATHER),
            explanation=f"Thunderstorm conditions (weather code {code}) are reported for this area.",
            guidance=[guidance_for(profile, RiskCategory.SEVERE_WEATHER, role)],
            affected_metric="weather_code",
            measured_value=float(code),
        )
    ]


def detect_flood_potential(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """FLOOD_POTENTIAL means weather conditions may increase flood risk.

    It does NOT mean flooding is observed — the explanation must keep that
    distinction clear to end users.
    """
    thresholds = profile.thresholds.flood_potential_mm_per_day
    bands = {"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme}
    rainfall = weather.rainfall_mm
    if rainfall < bands["moderate"]:
        return []
    severity = _band(rainfall, bands)
    return [
        RiskItem(
            category=RiskCategory.FLOOD_POTENTIAL,
            severity=severity,
            score=_score_from_severity(severity, rainfall, bands),
            title=_title(RiskCategory.FLOOD_POTENTIAL),
            explanation=(
                f"Rainfall of about {rainfall:.0f} mm may raise flood risk in low-lying or poorly drained areas. "
                "This indicates elevated flood potential — flooding is not confirmed or observed."
            ),
            guidance=[guidance_for(profile, RiskCategory.FLOOD_POTENTIAL, role)],
            affected_metric="flood_potential_mm_per_day",
            measured_value=rainfall,
        )
    ]


def detect_poor_travel_conditions(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Composite: rain + wind + storm codes together make travel poor even
    when each factor alone is below its own threshold."""
    bands = {"moderate": 20.0, "high": 45.0, "extreme": 75.0}
    context = _detection_context(weather)
    contributions: list[str] = []
    worst = Severity.LOW
    points = 0.0

    rain = context["rainfall_max"]
    if rain >= profile.thresholds.rainfall_mm_per_day.moderate:
        contributions.append(f"rainfall around {rain:.0f} mm")
        worst = max(worst, Severity.MODERATE, key=lambda s: s.rank)
        points += 20.0

    wind = context["wind_max"]
    if wind >= profile.thresholds.wind_kph.moderate:
        contributions.append(f"winds around {wind:.0f} km/h")
        worst = max(worst, Severity.MODERATE, key=lambda s: s.rank)
        points += 20.0

    code = context["code"]
    if isinstance(code, int) and code in set(profile.thresholds.severe_weather_codes):
        contributions.append("thunderstorm activity")
        worst = max(worst, Severity.HIGH, key=lambda s: s.rank)
        points += 25.0

    if not contributions:
        return []

    return [
        RiskItem(
            category=RiskCategory.POOR_TRAVEL_CONDITIONS,
            severity=worst,
            score=round(min(100.0, points + 10.0), 1),
            title=_title(RiskCategory.POOR_TRAVEL_CONDITIONS),
            explanation="Travel conditions are degraded by " + " and ".join(contributions) + ".",
            guidance=[guidance_for(profile, RiskCategory.POOR_TRAVEL_CONDITIONS, role)],
            affected_metric=None,
            measured_value=None,
        )
    ]


def detect_activity_disruption(weather: WeatherReading, profile: RiskProfile, role: str) -> list[RiskItem]:
    """Composite: outdoor plans are disrupted when any major condition
    (heavy rain, strong winds, storms, or dangerous heat) is present."""
    contributions: list[str] = []
    worst = Severity.LOW
    points = 0.0

    rain = weather.rainfall_mm
    if rain >= profile.thresholds.rainfall_mm_per_day.moderate:
        contributions.append(f"heavy rain ({rain:.0f} mm)")
        worst = max(worst, Severity.MODERATE, key=lambda s: s.rank)
        points += 20.0

    wind = max(weather.wind_kph, weather.wind_gust_kph or 0.0)
    if wind >= profile.thresholds.wind_kph.moderate:
        contributions.append(f"strong winds ({wind:.0f} km/h)")
        worst = max(worst, Severity.MODERATE, key=lambda s: s.rank)
        points += 20.0

    code = weather.weather_code
    if code is not None and code in set(profile.thresholds.severe_weather_codes):
        contributions.append("thunderstorm activity")
        worst = max(worst, Severity.HIGH, key=lambda s: s.rank)
        points += 25.0

    feels_like = weather.apparent_temperature_c if weather.apparent_temperature_c is not None else weather.temperature_c
    if feels_like >= profile.thresholds.apparent_temperature_c.high:
        contributions.append(f"dangerous heat ({feels_like:.0f}°C feels-like)")
        worst = max(worst, Severity.MODERATE, key=lambda s: s.rank)
        points += 20.0

    if not contributions:
        return []

    return [
        RiskItem(
            category=RiskCategory.ACTIVITY_DISRUPTION,
            severity=worst,
            score=round(min(100.0, points + 10.0), 1),
            title=_title(RiskCategory.ACTIVITY_DISRUPTION),
            explanation="Outdoor activities may be disrupted by " + ", ".join(contributions) + ".",
            guidance=[guidance_for(profile, RiskCategory.ACTIVITY_DISRUPTION, role)],
            affected_metric=None,
            measured_value=None,
        )
    ]


# Forecast-aware variants: run the same logic per forecast day. These keep
# the same thresholds so current and forecast risks agree with each other.
FORECAST_DETECTORS = {
    RiskCategory.RAINFALL: detect_rainfall,
    RiskCategory.HIGH_TEMPERATURE: detect_high_temperature,
    RiskCategory.HEAT_STRESS: detect_heat_stress,
}


def detect_forecast_risks(forecast: list[ForecastDay], profile: RiskProfile, role: str) -> list[RiskItem]:
    """Run forecast-capable detectors across each forecast day."""
    from app.services.weather.base import WeatherReading

    risks: list[RiskItem] = []
    for day in forecast:
        # Reuse the current-conditions detectors by synthesizing a reading
        # from the forecast day.
        reading = WeatherReading(
            location_label="forecast",
            latitude=0.0,
            longitude=0.0,
            observed_at=day.date,
            temperature_c=day.temperature_c,
            condition=day.condition or "Unknown",
            rainfall_mm=day.rainfall_mm,
            precip_probability_pct=day.precipitation_probability_pct or 0.0,
            humidity_pct=0.0,
            wind_kph=day.wind_max_kph or 0.0,
            source="forecast",
            is_verified=False,
            apparent_temperature_c=day.apparent_temperature_max_c,
        )
        for detector in FORECAST_DETECTORS.values():
            for risk in detector(reading, profile, role):
                risks.append(
                    RiskItem(
                        category=risk.category,
                        severity=risk.severity,
                        score=risk.score,
                        title=risk.title,
                        explanation=risk.explanation,
                        guidance=risk.guidance,
                        affected_metric=risk.affected_metric,
                        measured_value=risk.measured_value,
                        affected_day=day.date,
                    )
                )
    return risks
