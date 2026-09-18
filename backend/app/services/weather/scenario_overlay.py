"""
Judge-demo scenario overlay for LIVE weather providers.

The mock provider ships fixed per-scenario fixtures, but a public deployment
runs on `open_meteo`/`met_norway` — real data with no scenario knob. Judges
still need to SEE how the whole product reacts to heavy rain, heatwaves,
floods and smog, so this wrapper "bends" a live reading toward the scenario's
characteristics: the underlying observation stays real (coordinates, observed
time, provenance), while the measurements are blended toward the scenario
profile so every downstream consumer — risk engine, safety engine, chat
grounding, UI atmosphere — experiences the scenario exactly as it would in
nature.

Honesty is structural, not cosmetic:
- `is_verified` is forced False and `source` becomes "scenario_overlay:<name>",
  so the UI labels the card ESTIMATE and can never present simulated weather
  as live observations.
- The scenario is refused when the configured provider has no live data to
  bend (mock/fixture setups) — simulating a simulation is meaningless.
"""
import dataclasses

from app.services.weather.base import ForecastDay, WeatherProvider, WeatherReading


# Direction and magnitude per scenario. `max()` blending pulls the reading
# UP to at least the target (rainfall, wind, AQI, precip probability),
# `min()` pushes it DOWN to at most the target — chosen per field so the
# bend reads naturally instead of replacing the real value outright.
# Temperatures use a fixed set point: a heatwave demo must FEEL like 43 °C.
_SCENARIO_BENDS = {
    # field: (blend, target)
    "heavy_rainfall": {
        ("rainfall_mm", "max"): 68.0,
        ("precip_probability_pct", "max"): 92.0,
        ("humidity_pct", "max"): 88.0,
        ("wind_kph", "max"): 22.0,
    },
    "heatwave": {
        ("temperature_c", "set"): 43.0,
        ("apparent_temperature_c", "set"): 47.5,
        ("humidity_pct", "min"): 28.0,
        ("rainfall_mm", "set"): 0.0,
    },
    "thunderstorm": {
        ("rainfall_mm", "max"): 34.0,
        ("precip_probability_pct", "max"): 80.0,
        ("wind_kph", "max"): 38.0,
        ("wind_gust_kph", "max"): 55.0,
        ("humidity_pct", "max"): 78.0,
    },
    "flood_risk": {
        ("rainfall_mm", "max"): 110.0,
        ("precip_probability_pct", "set"): 97.0,
        ("humidity_pct", "max"): 91.0,
        ("wind_kph", "max"): 26.0,
    },
    "smog": {
        ("aqi_us", "set"): 168.0,
        ("wind_kph", "min"): 6.0,
        ("rainfall_mm", "set"): 0.0,
    },
}

SCENARIO_NAMES = tuple(_SCENARIO_BENDS)


class ScenarioOverlayProvider(WeatherProvider):
    """Wraps a live provider and bends every reading toward one scenario.

    Sits OUTSIDE the resilience layer on purpose: even a degraded (stale-
    cache) reading still bends, so the judge demo keeps working during an
    upstream outage — with the degraded/simulated labels stacking honestly.
    """

    def __init__(self, inner: WeatherProvider, scenario: str) -> None:
        self._inner = inner
        self._scenario = scenario

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        return bend_reading(await self._inner.get_current(latitude, longitude), self._scenario)

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        return bend_forecast(await self._inner.get_forecast(latitude, longitude, days=days), self._scenario)


def bend_reading(reading: WeatherReading, scenario: str) -> WeatherReading:
    """Return a copy of `reading` bent toward the scenario profile."""
    bends = _SCENARIO_BENDS.get(scenario)
    if bends is None:
        return reading

    updates: dict = {}
    for (field, blend), target in bends.items():
        if field.startswith("aqi_"):
            # Air quality is nested in reading.air_quality and handled by the
            # special case below — never a direct WeatherReading field.
            continue
        if blend == "set":
            updates[field] = target
        elif blend == "max":
            current = _field(reading, field)
            if current is not None:
                updates[field] = max(current, target)
        elif blend == "min":
            current = _field(reading, field)
            if current is not None:
                updates[field] = min(current, target)

    if scenario == "smog" and reading.air_quality is not None:
        # Real AQI enrichment exists: bend IT (keeps pm2.5/pm10 coherent),
        # provenance flipped to the overlay so it is never shown as live.
        aq = dataclasses.replace(
            reading.air_quality,
            us_aqi=168.0,
            pm2_5=round(168.0 * 0.45, 1),
            pm10=round(168.0 * 0.75, 1),
            source="scenario_overlay",
            is_verified=False,
        )
        updates["air_quality"] = aq
    elif scenario == "smog":
        # No live AQI enrichment (disabled upstream or failed): build the
        # simulated AQI explicitly — this is a judge demo, and the mock
        # provider ships the same fixture. Provenance says overlay, never live.
        from app.services.weather.air_quality import AirQuality, us_aqi_band
        from datetime import datetime, timezone

        updates["air_quality"] = AirQuality(
            observed_at=datetime.now(timezone.utc).isoformat(),
            us_aqi=168.0,
            pm2_5=round(168.0 * 0.45, 1),
            pm10=round(168.0 * 0.75, 1),
            band=us_aqi_band(168.0),
            source="scenario_overlay",
            is_verified=False,
        )

    return dataclasses.replace(
        reading,
        **updates,
        source=f"scenario_overlay:{scenario}",
        is_verified=False,  # structural honesty: never presented as live data
    )


def _field(reading: WeatherReading, field: str):
    return getattr(reading, field, None)


def bend_forecast(days: list[ForecastDay], scenario: str) -> list[ForecastDay]:
    """Bend a forecast the same way, so the demo's outlook matches the moment."""
    bends = _SCENARIO_BENDS.get(scenario)
    if bends is None:
        return days
    out = []
    for day in days:
        updates: dict = {}
        for (field, blend), target in bends.items():
            if field not in ("rainfall_mm", "temperature_c", "wind_kph"):
                continue
            forecast_field = {"wind_kph": "wind_max_kph"}.get(field, field)
            current = getattr(day, forecast_field, None)
            if blend == "set":
                updates[forecast_field] = target
            elif current is not None and blend == "max":
                updates[forecast_field] = max(current, target)
            elif current is not None and blend == "min":
                updates[forecast_field] = min(current, target)
        out.append(dataclasses.replace(day, **updates))
    return out
