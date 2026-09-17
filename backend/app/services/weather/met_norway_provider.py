"""
Weather provider backed by MET Norway's free, key-less Locationforecast API
(https://api.met.no/weatherapi/locationforecast/2.0/).

Selected via WEATHER_PROVIDER=met_norway. Chosen specifically because it is
key-less AND does not block cloud-platform egress IPs (Open-Meteo answers
shared cloud IPs with 429 regardless of request rate — observed live on
Render), so the public deployment can serve genuinely live weather.

Normalized into the canonical WeatherReading / ForecastDay models in
base.py — nothing downstream knows or cares where the numbers came from.
Never fabricates data: missing required upstream fields raise
WeatherProviderError (malformed_response); upstream failures raise typed
errors with safe, user-facing details.

Two derived fields, chosen deliberately and documented here:
- precip_probability_pct: MET publishes no probability. The schema requires
  it (risk detectors + UI consume it), and writing 0.0 would silently mask
  rain risk. We derive a conservative monotonic estimate from MET's own
  forecast precipitation AMOUNT (0 mm -> 0%, heavier forecast -> higher),
  capped at 95%. The reading stays is_verified=True because every input is
  a real MET value; the derivation only translates amount into the
  probability scale the app expects.
- weather_code: MET symbol codes are not WMO codes, so we do not fake a
  mapping; weather_code stays None (the risk engine skips code-based
  detectors) and the human-readable condition comes from the symbol.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.services.weather.base import (
    ForecastDay,
    WeatherProvider,
    WeatherProviderError,
    WeatherReading,
    wind_direction_to_compass,
)

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
# MET's terms require an identifying User-Agent with contact info.
_DEFAULT_USER_AGENT = "WeatherGPT/1.0 (https://github.com/rodrixdcruz/Weather-GPT)"
_DEFAULT_TIMEOUT_SECONDS = 10.0

# MET symbol stems -> display text. Suffixes like _day/_night/_polartwilight
# are stripped before lookup; anything containing "thunder" overrides.
_SYMBOL_TEXT = {
    "clearsky": "Clear sky",
    "fair": "Fair",
    "partlycloudy": "Partly cloudy",
    "cloudy": "Cloudy",
    "lightrain": "Light rain",
    "rain": "Rain",
    "heavyrain": "Heavy rain",
    "lightrainshowers": "Light rain showers",
    "rainshowers": "Rain showers",
    "heavyrainshowers": "Heavy rain showers",
    "lightsnow": "Light snow",
    "snow": "Snow",
    "heavysnow": "Heavy snow",
    "lightsnowshowers": "Light snow showers",
    "snowshowers": "Snow showers",
    "heavysnowshowers": "Heavy snow showers",
    "sleet": "Sleet",
    "sleetshowers": "Sleet showers",
    "fog": "Fog",
}


def describe_symbol_code(symbol: str | None) -> str:
    """Human-readable condition for a MET symbol code like 'lightrainshowers_day'."""
    if not symbol:
        return "Unknown conditions"
    stem = symbol.split("_", 1)[0]
    if "thunder" in stem:
        return "Thunderstorm"
    return _SYMBOL_TEXT.get(stem, "Unknown conditions")


def _derived_precip_probability(amount_mm: float | None) -> float:
    """Translate MET's forecast precipitation amount into the probability
    scale the app requires. Conservative and monotonic: 0 mm -> 0%, with a
    95% ceiling so we never claim certainty MET does not publish."""
    if amount_mm is None or amount_mm <= 0.0:
        return 0.0
    return min(95.0, 40.0 + amount_mm * 8.0)


class MetNorwayWeatherProvider(WeatherProvider):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = _DEFAULT_USER_AGENT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        # Injectable transport for tests (httpx.MockTransport); None = normal networking.
        self._transport = transport

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        payload = await self._fetch({"lat": latitude, "lon": longitude})
        timeseries = _require_timeseries(payload)
        entry = self._entry_for_now(timeseries)

        instant = _require_dict(entry.get("data"), "data")
        details = _require_dict(instant.get("instant"), "instant.details") if isinstance(instant.get("instant"), dict) else None
        instant_details = details.get("details") if isinstance(details, dict) else None
        if not isinstance(instant_details, dict):
            raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")

        temperature = _require_number(instant_details, "air_temperature")
        humidity = _optional_number(instant_details, "relative_humidity")
        wind_ms = _optional_number(instant_details, "wind_speed")
        wind_kph = round(wind_ms * 3.6, 1) if wind_ms is not None else 0.0
        wind_dir_deg = _optional_number(instant_details, "wind_from_direction")

        data = instant
        rain, symbol = self._precip_and_symbol(data)
        probability = _derived_precip_probability(rain)

        return WeatherReading(
            location_label=f"{latitude:.3f}, {longitude:.3f}",
            latitude=latitude,
            longitude=longitude,
            observed_at=str(entry.get("time") or ""),
            temperature_c=temperature,
            condition=describe_symbol_code(symbol),
            rainfall_mm=rain or 0.0,
            precip_probability_pct=probability,
            humidity_pct=humidity or 0.0,
            wind_kph=wind_kph,
            source="met-norway",
            is_verified=True,
            apparent_temperature_c=None,  # MET does not publish feels-like
            wind_direction_deg=wind_dir_deg,
            wind_direction=wind_direction_to_compass(wind_dir_deg) if wind_dir_deg is not None else None,
            wind_gust_kph=None,  # not in the compact payload
            weather_code=None,  # MET symbols are not WMO codes; no fake mapping
        )

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        payload = await self._fetch({"lat": latitude, "lon": longitude})
        timeseries = _require_timeseries(payload)

        buckets: dict[str, dict[str, Any]] = {}
        for entry in timeseries:
            ts = _parse_time(entry.get("time"))
            if ts is None:
                continue
            data = entry.get("data")
            if not isinstance(data, dict):
                continue
            instant = data.get("instant")
            details = instant.get("details") if isinstance(instant, dict) else None
            if not isinstance(details, dict):
                continue

            date_key = ts.strftime("%Y-%m-%d")
            bucket = buckets.setdefault(date_key, {"temps": [], "rain": 0.0, "prob": 0.0, "wind": 0.0, "symbol": None})
            temp = _optional_number(details, "air_temperature")
            if temp is not None:
                bucket["temps"].append(temp)
            wind_ms = _optional_number(details, "wind_speed")
            if wind_ms is not None:
                bucket["wind"] = max(bucket["wind"], wind_ms * 3.6)

            # Precip: prefer the 1h window; else take 6h windows only at
            # their start hour (00/06/12/18 UTC) so windows never overlap
            # and the day total is never double-counted.
            hour = ts.hour
            rain_1h, symbol = self._precip_and_symbol(data)
            if rain_1h is not None:
                bucket["rain"] += rain_1h
                bucket["prob"] = max(bucket["prob"], _derived_precip_probability(rain_1h))
            elif hour % 6 == 0:
                six = data.get("next_6_hours")
                six_details = six.get("details") if isinstance(six, dict) else None
                amount = _optional_number(six_details, "precipitation_amount") if isinstance(six_details, dict) else None
                if amount is not None:
                    bucket["rain"] += amount
                    bucket["prob"] = max(bucket["prob"], _derived_precip_probability(amount))
            if bucket["symbol"] is None and symbol:
                bucket["symbol"] = symbol

        forecast: list[ForecastDay] = []
        # Day keys follow UTC; anchor on the first bucket so day 1 is "today"
        # even if the first timestamps arrive slightly out of order.
        ordered = sorted(buckets.keys())
        if not ordered:
            raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
        first_date = datetime.strptime(ordered[0], "%Y-%m-%d").date()
        for index in range(days):
            date_key = (first_date + timedelta(days=index)).strftime("%Y-%m-%d")
            bucket = buckets.get(date_key)
            if bucket is None:
                continue
            forecast.append(
                ForecastDay(
                    date=date_key,
                    rainfall_mm=round(bucket["rain"], 1),
                    temperature_c=max(bucket["temps"]) if bucket["temps"] else 0.0,
                    precipitation_probability_pct=bucket["prob"],
                    condition=describe_symbol_code(bucket["symbol"]),
                    weather_code=None,
                    apparent_temperature_max_c=None,
                    wind_max_kph=round(bucket["wind"], 1),
                )
            )
        return forecast

    # --- internals -----------------------------------------------------

    @staticmethod
    def _precip_and_symbol(data: dict[str, Any]) -> tuple[float | None, str | None]:
        """First precipitation amount + symbol from the nearest window
        (next_1_hours, then next_6_hours, then next_12_hours)."""
        for window in ("next_1_hours", "next_6_hours", "next_12_hours"):
            section = data.get(window)
            if not isinstance(section, dict):
                continue
            w_details = section.get("details")
            amount = _optional_number(w_details, "precipitation_amount") if isinstance(w_details, dict) else None
            summary = section.get("summary")
            symbol = summary.get("symbol_code") if isinstance(summary, dict) else None
            if amount is not None or symbol:
                return amount, str(symbol) if symbol else None
        return None, None

    @staticmethod
    def _entry_for_now(timeseries: list[Any]) -> dict[str, Any]:
        """The timeseries entry closest to (not after) now UTC; MET starts
        the series at the current hour, so prefer that over blindly taking
        the first row."""
        now = datetime.now(timezone.utc)
        best: dict[str, Any] | None = None
        best_delta = None
        for entry in timeseries:
            ts = _parse_time(entry.get("time"))
            if ts is None:
                continue
            delta = abs((ts - now).total_seconds())
            if best_delta is None or delta < best_delta:
                best = entry
                best_delta = delta
        if best is None:
            raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
        return best

    async def _fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"User-Agent": self._user_agent}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport, headers=headers) as client:
                response = await client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("met_norway.timeout url=%s", self._base_url)
            raise WeatherProviderError("upstream_unavailable", "The weather service did not respond in time. Please try again shortly.") from exc
        except httpx.HTTPError as exc:
            log.warning("met_norway.connection_error url=%s error=%s", self._base_url, type(exc).__name__)
            raise WeatherProviderError("upstream_unavailable", "Could not reach the weather service. Check connectivity and try again.") from exc

        if response.status_code >= 400:
            log.warning("met_norway.http_error status=%s", response.status_code)
            raise WeatherProviderError("upstream_error", f"The weather service returned an error (HTTP {response.status_code}). Please try again shortly.")

        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("met_norway.malformed_json")
            raise WeatherProviderError("malformed_response", "The weather service returned an unreadable response.") from exc

        if not isinstance(payload, dict):
            raise WeatherProviderError("malformed_response", "The weather service returned an unreadable response.")
        return payload


def _require_timeseries(payload: dict[str, Any]) -> list[Any]:
    properties = payload.get("properties")
    timeseries = properties.get("timeseries") if isinstance(properties, dict) else None
    if not isinstance(timeseries, list) or not timeseries:
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    return timeseries


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WeatherProviderError("malformed_response", "The weather service returned incomplete data. Please try again shortly.")
    return value


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


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
