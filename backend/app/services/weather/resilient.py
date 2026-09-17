"""
Resilience layer for live weather providers.

Cloud platforms hand every app the same shared egress IPs, and key-less
public weather APIs answer those shared IPs with HTTP 429 long before any
single deployment's quota is gone (observed live: Open-Meteo rate-limited
Render's shared pool on every request). The raw provider turns that into a
user-facing 502; this wrapper turns it into graceful degradation:

- Shared short-TTL cache (coords rounded to ~1 km) so a popular location
  costs one upstream call per TTL window, process-wide.
- In-flight coalescing: concurrent misses for one location share a call.
- On failure: serve a recent cached reading (marked degraded=True) when one
  exists; otherwise degrade to the clearly-labeled mock fixture
  (is_verified=False -> the UI shows DEMO MODE) instead of an error.
- invalid_coordinates is never masked — bad input must fail loudly.

Nothing here fabricates "verified" data: degraded readings are real but
older than the fresh window; fixture readings carry exactly the labeling
the mock provider gives them. State is module-level because routers build
a provider per request — the cache must outlive individual instances.
"""
import asyncio
import logging
import time
from dataclasses import replace
from typing import Any

from app.services.weather.base import (
    ForecastDay,
    WeatherProvider,
    WeatherProviderError,
    WeatherReading,
)

log = logging.getLogger(__name__)

FRESH_TTL_SECONDS = 300.0       # serve from cache without an upstream call
STALE_MAX_SECONDS = 6 * 3600.0  # expired cache may still serve during an outage
DEGRADABLE_KINDS = frozenset({"upstream_unavailable", "upstream_error", "malformed_response"})

# Shared across provider instances (routers construct one per request).
_current_cache: dict[tuple[float, float], tuple[WeatherReading, float]] = {}
_forecast_cache: dict[tuple[float, float, int], tuple[list[ForecastDay], float]] = {}
_current_inflight: dict[tuple[float, float], asyncio.Task] = {}
_forecast_inflight: dict[tuple[float, float, int], asyncio.Task] = {}
_fixture_provider: WeatherProvider | None = None


def reset_state_for_tests() -> None:
    """Clear all shared state (test isolation only)."""
    global _fixture_provider
    _current_cache.clear()
    _forecast_cache.clear()
    _current_inflight.clear()
    _forecast_inflight.clear()
    _fixture_provider = None


def _fixture() -> WeatherProvider:
    global _fixture_provider
    if _fixture_provider is None:
        from app.services.weather.mock_provider import MockWeatherProvider

        _fixture_provider = MockWeatherProvider("normal")
    return _fixture_provider


class ResilientWeatherProvider(WeatherProvider):
    def __init__(
        self,
        inner: WeatherProvider,
        *,
        fresh_ttl_seconds: float = FRESH_TTL_SECONDS,
        stale_max_seconds: float = STALE_MAX_SECONDS,
    ) -> None:
        self._inner = inner
        self._fresh_ttl = fresh_ttl_seconds
        self._stale_max = stale_max_seconds

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        key = (round(latitude, 2), round(longitude, 2))
        entry = _current_cache.get(key)
        if entry is not None and (time.monotonic() - entry[1]) < self._fresh_ttl:
            return replace(entry[0])

        task = _current_inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._get_current_resilient(latitude, longitude, key))
            _current_inflight[key] = task
        try:
            return await task
        finally:
            # Only pop while we still own the slot: a concurrent creator may
            # have replaced it after our task finished.
            if _current_inflight.get(key) is task:
                _current_inflight.pop(key, None)

    async def _get_current_resilient(self, latitude: float, longitude: float, key) -> WeatherReading:
        try:
            reading = await self._inner.get_current(latitude, longitude)
        except WeatherProviderError as exc:
            if exc.kind not in DEGRADABLE_KINDS:
                raise
            entry = _current_cache.get(key)
            if entry is not None and (time.monotonic() - entry[1]) <= self._stale_max:
                age_s = int(time.monotonic() - entry[1])
                log.warning(
                    "weather.degraded kind=stale_cache provider_error=%s age_s=%d lat=%.2f lon=%.2f",
                    exc.kind, age_s, latitude, longitude,
                )
                return replace(entry[0], degraded=True)
            log.warning(
                "weather.degraded kind=fixture provider_error=%s lat=%.2f lon=%.2f",
                exc.kind, latitude, longitude,
            )
            return await _fixture().get_current(latitude, longitude)
        _current_cache[key] = (reading, time.monotonic())
        return reading

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        key = (round(latitude, 2), round(longitude, 2), days)
        entry = _forecast_cache.get(key)
        if entry is not None and (time.monotonic() - entry[1]) < self._fresh_ttl:
            return list(entry[0])

        task = _forecast_inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._get_forecast_resilient(latitude, longitude, key, days))
            _forecast_inflight[key] = task
        try:
            return await task
        finally:
            if _forecast_inflight.get(key) is task:
                _forecast_inflight.pop(key, None)

    async def _get_forecast_resilient(
        self, latitude: float, longitude: float, key, days: int
    ) -> list[ForecastDay]:
        try:
            forecast = await self._inner.get_forecast(latitude, longitude, days=days)
        except WeatherProviderError as exc:
            if exc.kind not in DEGRADABLE_KINDS:
                raise
            entry = _forecast_cache.get(key)
            if entry is not None and (time.monotonic() - entry[1]) <= self._stale_max:
                log.warning(
                    "weather.degraded_forecast kind=stale_cache provider_error=%s lat=%.2f lon=%.2f",
                    exc.kind, latitude, longitude,
                )
                return list(entry[0])
            log.warning(
                "weather.degraded_forecast kind=fixture provider_error=%s lat=%.2f lon=%.2f",
                exc.kind, latitude, longitude,
            )
            return await _fixture().get_forecast(latitude, longitude, days=days)
        _forecast_cache[key] = (forecast, time.monotonic())
        return forecast
