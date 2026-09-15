"""Shared test fixtures. No test ever hits the live Open-Meteo API."""
import pytest

from app.services.risk.baseline import reset_baseline_provider
from app.services.risk.profile import get_risk_profile
from app.services.risk.roles import normalize_role
from app.services.weather.base import WeatherProviderError, WeatherReading


class StubProvider:
    """Provider double that always returns a fixed reading or raises."""

    def __init__(self, reading=None, error: WeatherProviderError | None = None):
        self._reading = reading
        self._error = error

    async def get_current(self, latitude, longitude):
        if self._error:
            raise self._error
        return self._reading

    async def get_forecast(self, latitude, longitude, days=7):
        if self._error:
            raise self._error
        return []


def _calm_reading() -> WeatherReading:
    return WeatherReading(
        location_label="19.076, 72.878",
        latitude=19.076,
        longitude=72.8777,
        observed_at="2026-09-09T06:00",
        temperature_c=29.0,
        condition="Partly cloudy",
        rainfall_mm=2.0,
        precip_probability_pct=10.0,
        humidity_pct=55.0,
        wind_kph=12.0,
        source="test",
        is_verified=False,
    )


@pytest.fixture
def client():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def stub_calm_provider(monkeypatch):
    """Replace the weather provider everywhere with a calm-conditions stub."""
    from app.api.v1.routers import chat as chat_router
    from app.api.v1.routers import risk as risk_router
    from app.api.v1.routers import safety as safety_router
    from app.api.v1.routers import weather as weather_router

    provider = StubProvider(reading=_calm_reading())
    for module in (weather_router, risk_router, safety_router, chat_router):
        monkeypatch.setattr(module, "get_weather_provider", lambda scenario="normal", _p=provider: _p)
    return provider


@pytest.fixture(autouse=True)
def _clean_baseline_cache():
    reset_baseline_provider()
    yield
    reset_baseline_provider()


@pytest.fixture
def profile():
    return get_risk_profile("default")


@pytest.fixture
def reading_factory():
    """Build WeatherReadings with sensible defaults; tests override per case."""

    def _make(**overrides) -> WeatherReading:
        base = dict(
            location_label="19.076, 72.878",
            latitude=19.076,
            longitude=72.8777,
            observed_at="2026-09-09T06:00",
            temperature_c=29.0,
            condition="Partly cloudy",
            rainfall_mm=2.0,
            precip_probability_pct=10.0,
            humidity_pct=55.0,
            wind_kph=12.0,
            source="test_fixture",
            is_verified=False,
            apparent_temperature_c=31.0,
            wind_direction_deg=275.0,
            wind_direction="W",
            wind_gust_kph=None,
            weather_code=2,
        )
        base.update(overrides)
        return WeatherReading(**base)

    return _make


@pytest.fixture
def role():
    return normalize_role(None)  # default role
