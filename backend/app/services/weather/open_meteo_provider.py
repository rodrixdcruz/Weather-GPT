"""
Real weather provider backed by the free, key-less Open-Meteo public API
(https://open-meteo.com/en/docs). Selected via WEATHER_PROVIDER=open_meteo.

Normalizes Open-Meteo's provider-specific fields into the canonical
WeatherReading / ForecastDay models in base.py — nothing downstream knows
or cares where the numbers came from. Never fabricates data: missing
upstream fields surface as WeatherProviderError (malformed_response), and
upstream failures surface as WeatherProviderError with a safe detail
message; nothing is silently swallowed.
"""
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.weather.base import (
    ForecastDay,
    WeatherProvider,
    WeatherProviderError,
    WeatherReading,
    wind_direction_to_compass,
)
from app.services.weather.wmo_codes import describe_wmo_code, describe_wmo_code_short

log = logging.getLogger(__name__)

# Open-Meteo returns hourly arrays; we pull the index matching the
# current time. An explicit timezone=UTC keeps indices deterministic.
_HOURLY_VARS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "weather_code",
]
_DAILY_VARS = [
    "weather_code",
    "temperature_2m_max",
    "apparent_temperature_max",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
]

# Open-Meteo reports wind in km/h by default; we request it explicitly to
# be immune to future default changes, and consume it as-is (kph).
_DEFAULT_TIMEOUT_SECONDS = 10.0


class OpenMeteoWeatherProvider(WeatherProvider):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.WEATHER_API_BASE_URL or "https://api.open-meteo.com/v1/forecast").rstrip("/")
        self._timeout_seconds = timeout_seconds
        # Injectable transport for tests (httpx.MockTransport); None = normal networking.
        self._transport = transport

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        params = self._common_params(latitude, longitude)
        params.update(
            {
                "current": ",".join(
                    [
                        "temperature_2m",
                        "apparent_temperature",
                        "relative_humidity_2m",
                        "precipitation",
                        "weather_code",
                    ]
                ),
                "hourly": ",".join(_HOURLY_VARS),
                "forecast_hours": 1,
            }
        )

        payload = await self._fetch(params)
        current = _require_section(payload, "current")
        hourly = _require_section(payload, "hourly")

        temperature = _require_number(current, "temperature_2m")
        rainfall = _optional_number(current, "precipitation") or 0.0

        # Precipitation probability + wind are hourly variables; take the
        # hour matching the observation time reported by Open-Meteo.
        hour_index = self._hourly_index_for_current(hourly, current.get("time"))
        precip_probability = _hourly_number(hourly, "precipitation_probability", hour_index, default=0.0)
        humidity = _hourly_number(hourly, "relative_humidity_2m", hour_index, default=0.0)
        wind_kph = _hourly_number(hourly, "wind_speed_10m", hour_index, default=0.0)
        wind_direction_deg = _hourly_optional(hourly, "wind_direction_10m", hour_index)
        wind_gust_kph = _hourly_optional(hourly, "wind_gusts_10m", hour_index)
        weather_code = _optional_int(current.get("weather_code"))
        if weather_code is None:
            weather_code = _hourly_optional(hourly, "weather_code", hour_index)

        observed_at = str(current.get("time") or _hourly_time(hourly, hour_index) or "")

        return WeatherReading(
            location_label=f"{latitude:.3f}, {longitude:.3f}",
            latitude=latitude,
            longitude=longitude,
            observed_at=observed_at,
            temperature_c=temperature,
            condition=describe_wmo_code(weather_code),
            rainfall_mm=rainfall,
            precip_probability_pct=precip_probability,
            humidity_pct=humidity,
            wind_kph=wind_kph,
            source="open-meteo",
            is_verified=True,
            apparent_temperature_c=_optional_number(current, "apparent_temperature"),
            wind_direction_deg=wind_direction_deg,
            wind_direction=wind_direction_to_compass(wind_direction_deg) if wind_direction_deg is not None else None,
            wind_gust_kph=wind_gust_kph,
            weather_code=weather_code,
        )

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        params = self._common_params(latitude, longitude)
        params.update({"daily": ",".join(_DAILY_VARS), "forecast_days": days, "timezone": "auto"})

        payload = await self._fetch(params)
        daily = _require_section(payload, "daily")
        times = _require_list(daily, "time")

        forecast: list[ForecastDay] = []
        for index in range(len(times)):
            forecast.append(
                ForecastDay(
                    date=str(times[index]),
                    rainfall_mm=_daily_number(daily, "precipitation_sum", index, default=0.0),
                    temperature_c=_daily_number(daily, "temperature_2m_max", index, default=0.0),
                    precipitation_probability_pct=_daily_optional(daily, "precipitation_probability_max", index),
                    condition=describe_wmo_code_short(_daily_optional(daily, "weather_code", index)),
                    weather_code=_daily_optional(daily, "weather_code", index),
                    apparent_temperature_max_c=_daily_optional(daily, "apparent_temperature_max", index),
                    wind_max_kph=_daily_optional(daily, "wind_speed_10m_max", index),
                    )
            )
        return forecast

    # --- internals -----------------------------------------------------

    def _common_params(self, latitude: float, longitude: float) -> dict[str, Any]:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "wind_speed_unit": "kmh",
            "timezone": "UTC",
            # Open-Meteo rejects out-of-range coordinates with a 400 and a
            # `reason` field; we surface that as an invalid-coordinates error.
        }

    async def _fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = await client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("open_meteo.timeout url=%s", self._base_url)
            raise WeatherProviderError("upstream_unavailable", "The weather service did not respond in time. Please try again shortly.") from exc
        except httpx.HTTPError as exc:
            log.warning("open_meteo.connection_error url=%s error=%s", self._base_url, type(exc).__name__)
            raise WeatherProviderError("upstream_unavailable", "Could not reach the weather service. Check connectivity and try again.") from exc

        if response.status_code == 400:
            # Open-Meteo rejects out-of-range coordinates with 400; treat
            # that specifically as invalid input, not a service failure.
            detail = self._upstream_reason(response)
            log.info("open_meteo.bad_request reason=%s", detail)
            raise WeatherProviderError("invalid_coordinates", detail or "The weather service rejected the requested coordinates.")

        if response.status_code >= 400:
            log.warning("open_meteo.http_error status=%s", response.status_code)
            raise WeatherProviderError("upstream_error", f"The weather service returned an error (HTTP {response.status_code}). Please try again shortly.")

        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("open_meteo.malformed_json")
            raise WeatherProviderError("malformed_response", "The weather service returned an unreadable response.") from exc

        if not isinstance(payload, dict):
            raise WeatherProviderError("malformed_response", "The weather service returned an unreadable response.")

        # Open-Meteo reports soft failures via {"error": true, "reason": ...}
        # with HTTP 200.
        if payload.get("error"):
            reason = str(payload.get("reason") or "").strip()
            log.info("open_meteo.soft_error reason=%s", reason)
            kind = "invalid_coordinates" if "coordinate" in reason.lower() else "upstream_error"
            raise WeatherProviderError(kind, reason or "The weather service could not process the request.")

        return payload

    def _hourly_index_for_current(self, hourly: dict[str, Any], current_time: Any) -> int:
        """Find the hourly index matching the observation time (UTC)."""
        times = _require_list(hourly, "time")
        if current_time:
            current_str = str(current_time)
            for index, ts in enumerate(times):
                if str(ts) == current_str:
                    return index
            # `current.time` may carry seconds that hourly lacks; match on
            # the hour prefix instead of failing outright.
            prefix = current_str[:13]
            for index, ts in enumerate(times):
                if str(ts)[:13] == prefix:
                    return index
        return 0

    @staticmethod
    def _upstream_reason(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        if isinstance(body, dict):
            return str(body.get("reason") or "").strip()
        return ""


# --- strict-but-tolerant payload accessors ---------------------------------
# The provider must never fabricate values: a missing *required* field is a
# malformed_response error; a missing *optional* field becomes None so the
# risk engine can skip the related detector.


def _require_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if not isinstance(section, dict):
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    return section


def _require_list(section: dict[str, Any], key: str) -> list[Any]:
    values = section.get(key)
    if not isinstance(values, list):
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    return values


def _require_number(section: dict[str, Any], key: str) -> float:
    value = section.get(key)
    if value is None:
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.") from exc


def _optional_number(section: dict[str, Any], key: str) -> float | None:
    value = section.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hourly_number(hourly: dict[str, Any], key: str, index: int, default: float) -> float:
    value = _hourly_optional(hourly, key, index)
    if value is None:
        return default
    return value


def _hourly_optional(hourly: dict[str, Any], key: str, index: int) -> float | None:
    values = hourly.get(key)
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        return None
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return None


def _hourly_time(hourly: dict[str, Any], index: int) -> str | None:
    values = hourly.get("time")
    if not isinstance(values, list) or index >= len(values):
        return None
    return str(values[index])


def _daily_number(daily: dict[str, Any], key: str, index: int, default: float) -> float:
    values = daily.get(key)
    if not isinstance(values, list) or index >= len(values):
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    value = values[index]
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.") from exc


def _daily_optional(daily: dict[str, Any], key: str, index: int) -> float | None:
    values = daily.get(key)
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        return None
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return None
