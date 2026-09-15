"""
Air-quality service backed by Open-Meteo's key-less Air Quality API
(https://open-meteo.com/en/docs/air-quality-api, CAMS model data).

Design rules inherited from the weather layer:
- Never fabricates data. Missing required fields raise
  AirQualityProviderError with a sanitized detail; optional fields
  become None so downstream can say "not available".
- All failures raise typed errors — nothing is silently swallowed.
- Injectable httpx transport so tests never hit the live API.
- US AQI is requested explicitly (unit=us_aqindex) for international
  comparability; the European AQI is also available when needed.
"""
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 8.0
_DEFAULT_BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Open-Meteo exposes US AQI sub-indices; we surface the headline index
# plus PM2.5 / PM10 (the two pollutants users hear about most).
_AQI_VARS = ["us_aqi", "pm2_5", "pm10"]

# US EPA AQI breakpoints for the band label shown to users. Threshold
# mapping for RISK DETECTION stays in the risk profile — this table is
# display-only, so air-quality facts never depend on risk config.
_US_AQI_BANDS = (
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for sensitive groups"),
    (200, "Unhealthy"),
    (300, "Very unhealthy"),
    (500, "Hazardous"),
)


@dataclass
class AirQuality:
    """Normalized air quality for one point at one hour.

    Follows the WeatherReading convention: `source`/`is_verified` travel
    with the data so the UI can label provenance honestly.
    """

    observed_at: str  # ISO 8601 hour reported by the provider
    us_aqi: float
    pm2_5: float | None = None
    pm10: float | None = None
    band: str | None = None  # human-readable band label (display-only)
    source: str = "open-meteo-air-quality"
    is_verified: bool = True  # CAMS is model data, but authoritative upstream


def us_aqi_band(us_aqi: float) -> str:
    """Map a US AQI value to its EPA band label (display-only)."""
    for ceiling, label in _US_AQI_BANDS:
        if us_aqi <= ceiling:
            return label
    return _US_AQI_BANDS[-1][1]


class AirQualityProviderError(Exception):
    """Raised when the air-quality provider cannot return usable data.

    Same contract as WeatherProviderError: machine-readable `kind` plus a
    pre-sanitized, user-safe `detail` — nothing upstream ever leaks.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class OpenMeteoAirQualityProvider:
    """Key-less Open-Meteo air-quality client (CAMS data)."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    async def get_current(self, latitude: float, longitude: float) -> AirQuality:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(_AQI_VARS),
            "timezone": "UTC",
        }
        payload = await self._fetch(params)
        current = payload.get("current")
        if not isinstance(current, dict):
            raise AirQualityProviderError("malformed_response", "The air-quality service returned incomplete data.")

        us_aqi = _optional_number(current, "us_aqi")
        if us_aqi is None:
            # The provider itself has no coverage/model value here — that is
            # "no data", not an error: enrichment will simply skip AQI.
            log.info("air_quality.no_data lat=%.3f lon=%.3f", latitude, longitude)
            raise AirQualityProviderError("no_data", "Air-quality data is not available for this location right now.")

        return AirQuality(
            observed_at=str(current.get("time") or ""),
            us_aqi=us_aqi,
            pm2_5=_optional_number(current, "pm2_5"),
            pm10=_optional_number(current, "pm10"),
            band=us_aqi_band(us_aqi),
            source="open-meteo-air-quality",
            is_verified=True,
        )

    async def _fetch(self, params: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = await client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("air_quality.timeout url=%s", self._base_url)
            raise AirQualityProviderError("upstream_unavailable", "The air-quality service did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("air_quality.connection_error url=%s error=%s", self._base_url, type(exc).__name__)
            raise AirQualityProviderError("upstream_unavailable", "Could not reach the air-quality service.") from exc

        if response.status_code >= 400:
            log.warning("air_quality.http_error status=%s", response.status_code)
            raise AirQualityProviderError("upstream_error", f"The air-quality service returned an error (HTTP {response.status_code}).")

        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("air_quality.malformed_json")
            raise AirQualityProviderError("malformed_response", "The air-quality service returned an unreadable response.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
            raise AirQualityProviderError("malformed_response", "The air-quality service returned an unreadable response.")
        return payload


def _optional_number(section: dict, key: str) -> float | None:
    value = section.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def attach_air_quality(reading, air_quality_provider) -> object:
    """Best-effort AQI enrichment for a normalized WeatherReading.

    Mirrors the safety-provider contract: an air-quality failure must
    NEVER break weather. Any AirQualityProviderError is logged and the
    original reading is returned unchanged; only genuine success attaches
    real provider data (never fabricated). The weather provider wires
    this itself, so callers (routes) need no changes and tests that
    construct providers directly get no enrichment.
    """
    if air_quality_provider is None:
        return reading
    from app.services.weather.base import WeatherReading

    try:
        aqi = await air_quality_provider.get_current(reading.latitude, reading.longitude)
    except AirQualityProviderError as exc:
        log.info("air_quality.enrich_skipped kind=%s detail=%s", exc.kind, exc.detail)
        return reading
    except Exception as exc:  # noqa: BLE001 - enrichment is strictly optional
        log.warning("air_quality.enrich_unexpected error=%s", type(exc).__name__)
        return reading

    return WeatherReading(**{**reading.__dict__, "air_quality": aqi})
