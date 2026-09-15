"""Mock weather provider compatibility: same contract, richer fields."""
import pytest

from app.services.weather.base import WeatherReading
from app.services.weather.factory import get_weather_provider
from app.services.weather.mock_provider import MockWeatherProvider


@pytest.mark.asyncio
async def test_mock_current_returns_canonical_reading():
    provider = MockWeatherProvider(scenario="normal")
    reading = await provider.get_current(19.076, 72.8777)
    assert isinstance(reading, WeatherReading)
    assert reading.is_verified is False
    assert reading.source == "mock_fixture"
    assert reading.temperature_c == 29.0
    assert reading.condition == "Partly cloudy"
    assert reading.wind_direction == "W"  # 275 degrees
    assert reading.weather_code == 2


@pytest.mark.asyncio
async def test_mock_unknown_scenario_falls_back_to_normal():
    provider = MockWeatherProvider(scenario="does_not_exist")
    reading = await provider.get_current(19.076, 72.8777)
    assert reading.temperature_c == 29.0


@pytest.mark.asyncio
async def test_mock_forecast_respects_days():
    provider = MockWeatherProvider()
    forecast = await provider.get_forecast(19.076, 72.8777, days=5)
    assert len(forecast) == 5
    assert all(day.precipitation_probability_pct is not None for day in forecast)


def test_mock_scenario_selected_via_factory(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "mock")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = get_weather_provider(scenario="heatwave")
        assert type(provider).__name__ == "MockWeatherProvider"
    finally:
        get_settings.cache_clear()
        monkeypatch.delenv("WEATHER_PROVIDER", raising=False)
        get_settings.cache_clear()
