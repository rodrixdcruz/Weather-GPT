"""Resilience-layer tests. All HTTP is mocked; nothing hits the live API."""
import asyncio

import httpx
import pytest

from app.services.weather.base import WeatherProvider, WeatherProviderError, WeatherReading
from app.services.weather.mock_provider import MockWeatherProvider
from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.services.weather.resilient import ResilientWeatherProvider, reset_state_for_tests


def _reading(latitude: float = 19.08, longitude: float = 72.88, temp: float = 25.5) -> WeatherReading:
    return WeatherReading(
        location_label=f"{latitude:.3f}, {longitude:.3f}",
        latitude=latitude,
        longitude=longitude,
        observed_at="2026-09-17T06:00",
        temperature_c=temp,
        condition="Clear sky",
        rainfall_mm=0.0,
        precip_probability_pct=0.0,
        humidity_pct=60.0,
        wind_kph=8.0,
        source="open-meteo",
        is_verified=True,
    )


class FlakyProvider(WeatherProvider):
    """Fails N times per operation kind, then succeeds (calls counted)."""

    def __init__(self, fail_times: int = 0, kind: str = "upstream_error") -> None:
        self.fail_times = fail_times
        self.kind = kind
        self.current_calls = 0
        self.forecast_calls = 0

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        self.current_calls += 1
        if self.current_calls <= self.fail_times:
            raise WeatherProviderError(self.kind, "boom")
        return _reading(latitude, longitude)

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list:
        self.forecast_calls += 1
        if self.forecast_calls <= self.fail_times:
            raise WeatherProviderError(self.kind, "boom")
        return [type("F", (), {"date": "d1"})()]


@pytest.fixture(autouse=True)
def _clean_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_passes_through_and_caches(self):
        inner = FlakyProvider()
        provider = ResilientWeatherProvider(inner)
        r1 = await provider.get_current(19.08, 72.88)
        r2 = await provider.get_current(19.08, 72.88)
        assert inner.current_calls == 1  # second hit served from cache
        assert r1.temperature_c == r2.temperature_c == 25.5
        assert r1.is_verified is True
        assert r1.degraded is False

    @pytest.mark.asyncio
    async def test_nearby_coordinates_share_cache(self):
        inner = FlakyProvider()
        provider = ResilientWeatherProvider(inner)
        await provider.get_current(19.076, 72.8777)
        await provider.get_current(19.079, 72.879)  # rounds to the same ~1km cell
        assert inner.current_calls == 1

    @pytest.mark.asyncio
    async def test_concurrent_misses_coalesce(self):
        class SlowProvider(FlakyProvider):
            async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
                self.current_calls += 1
                await asyncio.sleep(0.05)
                # Return directly: super() would double-count this class's
                # increment, so the coalescing assertion would read 2 == 1 call.
                return _reading(latitude, longitude)

        inner = SlowProvider()
        provider = ResilientWeatherProvider(inner)
        results = await asyncio.gather(*(provider.get_current(19.08, 72.88) for _ in range(5)))
        assert inner.current_calls == 1
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_forecast_caches(self):
        inner = FlakyProvider()
        provider = ResilientWeatherProvider(inner)
        await provider.get_forecast(19.08, 72.88, days=3)
        await provider.get_forecast(19.08, 72.88, days=3)
        assert inner.forecast_calls == 1


class TestDegradation:
    @pytest.mark.asyncio
    async def test_cold_non_degradable_failure_raises(self):
        # From a cold start, a non-degradable error (bad input) must surface
        # — only transient upstream kinds may degrade to fixture data.
        provider = ResilientWeatherProvider(FlakyProvider(kind="invalid_coordinates", fail_times=99))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.08, 72.88)
        assert excinfo.value.kind == "invalid_coordinates"

    @pytest.mark.asyncio
    async def test_failure_after_success_serves_stale_cache(self):
        inner = FlakyProvider()  # succeeds first, filling the cache
        # fresh_ttl <= 0 disables fresh-cache hits so the second call reaches
        # the (now failing) inner provider; stale_max keeps the entry servable.
        provider = ResilientWeatherProvider(inner, fresh_ttl_seconds=-1, stale_max_seconds=3600)
        await provider.get_current(19.08, 72.88)
        inner.fail_times = 99  # now always fails
        r = await provider.get_current(19.08, 72.88)
        assert r.degraded is True
        assert r.is_verified is True  # real data, just older
        assert r.temperature_c == 25.5

    @pytest.mark.asyncio
    async def test_invalid_coordinates_never_masked(self):
        inner = FlakyProvider()
        # Bypass the fresh window (see stale-cache test) so the second call
        # actually reaches the provider and its bad-input error surfaces.
        provider = ResilientWeatherProvider(inner, fresh_ttl_seconds=-1, stale_max_seconds=3600)
        await provider.get_current(19.08, 72.88)  # fill cache with a good reading
        inner.fail_times = 99
        inner.kind = "invalid_coordinates"
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.08, 72.88)
        assert excinfo.value.kind == "invalid_coordinates"

    @pytest.mark.asyncio
    async def test_persistent_failure_from_cold_serves_labeled_fixture(self):
        inner = FlakyProvider(fail_times=99)
        provider = ResilientWeatherProvider(inner)
        r = await provider.get_current(19.08, 72.88)
        assert r.source == "mock_fixture"
        assert r.is_verified is False  # UI shows DEMO MODE, honest labeling
        assert r.degraded is False

    @pytest.mark.asyncio
    async def test_forecast_degrades_to_fixture(self):
        provider = ResilientWeatherProvider(FlakyProvider(fail_times=99))
        forecast = await provider.get_forecast(19.08, 72.88, days=3)
        assert len(forecast) == 3


class TestRateLimitRetry:
    @pytest.mark.asyncio
    async def test_429_retried_once_then_success(self, monkeypatch):
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("app.services.weather.open_meteo_provider.asyncio.sleep", fake_sleep)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={"error": True, "reason": "too many"})
            return httpx.Response(200, json=_open_meteo_ok())

        provider = OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))
        reading = await provider.get_current(19.076, 72.8777)
        assert calls["n"] == 2
        assert reading.temperature_c == 25.5
        assert len(sleeps) == 1

    @pytest.mark.asyncio
    async def test_429_twice_surfaces_as_upstream_error(self, monkeypatch):
        async def fake_sleep(delay: float) -> None:
            return None

        monkeypatch.setattr("app.services.weather.open_meteo_provider.asyncio.sleep", fake_sleep)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": True, "reason": "too many"})

        provider = OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_error"


def _open_meteo_ok() -> dict:
    return {
        "current": {
            "time": "2026-09-17T06:00",
            "temperature_2m": 25.5,
            "apparent_temperature": 31.3,
            "relative_humidity_2m": 84,
            "precipitation": 0.4,
            "weather_code": 95,
        },
        "hourly": {
            "time": ["2026-09-17T05:00", "2026-09-17T06:00"],
            "temperature_2m": [25.0, 25.5],
            "relative_humidity_2m": [86, 84],
            "precipitation": [0.0, 0.4],
            "precipitation_probability": [20, 65],
            "wind_speed_10m": [8.1, 12.4],
            "wind_direction_10m": [270, 315],
            "wind_gusts_10m": [14.2, 19.8],
            "weather_code": [2, 95],
        },
    }
