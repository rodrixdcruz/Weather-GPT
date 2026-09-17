"""MET Norway provider tests. All HTTP is mocked; nothing hits the live API."""
from datetime import datetime, timezone

import httpx
import pytest

from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider
from app.services.weather.met_norway_provider import (
    MetNorwayWeatherProvider,
    _derived_precip_probability,
    describe_symbol_code,
)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    """Freeze the provider's clock: _entry_for_now() picks the timeseries
    entry closest to *now*, so a moving wall clock makes fixed test
    timestamps flip between rows. 09:15 keeps entry0 (09:00) strictly
    closest to its 10:00 successor."""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 17, 9, 15, tzinfo=timezone.utc)

    monkeypatch.setattr("app.services.weather.met_norway_provider.datetime", _FixedDatetime)


def _met_payload():
    """Shape mirrors the live compact payload (timeseries + instant details)."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [72.8777, 19.076, 8]},
        "properties": {
            "meta": {"updated_at": "2026-09-17T08:18:11Z"},
            "timeseries": [
                {
                    "time": "2026-09-17T09:00:00Z",
                    "data": {
                        "instant": {"details": {
                            "air_pressure_at_sea_level": 1009.1,
                            "air_temperature": 29.7,
                            "cloud_area_fraction": 65.6,
                            "relative_humidity": 73.0,
                            "wind_from_direction": 240.9,
                            "wind_speed": 5.2,
                        }},
                        "next_12_hours": {"summary": {"symbol_code": "lightrain"}, "details": {}},
                        "next_1_hours": {"summary": {"symbol_code": "lightrainshowers_day"}, "details": {"precipitation_amount": 0.2}},
                        "next_6_hours": {"summary": {"symbol_code": "cloudy"}, "details": {"precipitation_amount": 0.4}},
                    },
                },
                {
                    "time": "2026-09-17T10:00:00Z",
                    "data": {
                        "instant": {"details": {"air_temperature": 29.6, "relative_humidity": 72.8, "wind_from_direction": 248.4, "wind_speed": 4.8}},
                        "next_1_hours": {"summary": {"symbol_code": "partlycloudy_day"}, "details": {"precipitation_amount": 0.0}},
                    },
                },
            ],
        },
    }


def _provider_with_payload(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("user-agent"), "MET terms require an identifying User-Agent"
        return httpx.Response(status_code, json=payload)

    return MetNorwayWeatherProvider(transport=httpx.MockTransport(handler))


class TestCurrentMapping:
    @pytest.mark.asyncio
    async def test_current_maps_all_fields(self):
        provider = _provider_with_payload(_met_payload())
        reading = await provider.get_current(19.076, 72.8777)

        assert reading.temperature_c == 29.7
        assert reading.humidity_pct == 73.0
        assert reading.wind_kph == 18.7  # 5.2 m/s * 3.6
        assert reading.wind_direction_deg == 240.9
        assert reading.rainfall_mm == 0.2  # from next_1_hours
        assert reading.condition == "Light rain showers"  # symbol stem
        assert reading.source == "met-norway"
        assert reading.is_verified is True
        assert reading.observed_at == "2026-09-17T09:00:00Z"

    @pytest.mark.asyncio
    async def test_probability_derived_from_amount(self):
        provider = _provider_with_payload(_met_payload())
        reading = await provider.get_current(19.076, 72.8777)
        assert 0.0 < reading.precip_probability_pct < 95.0

    @pytest.mark.asyncio
    async def test_no_rain_is_zero_probability(self):
        payload = _met_payload()
        payload["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"]["precipitation_amount"] = 0.0
        provider = _provider_with_payload(payload)
        reading = await provider.get_current(19.076, 72.8777)
        assert reading.precip_probability_pct == 0.0
        assert reading.rainfall_mm == 0.0

    @pytest.mark.asyncio
    async def test_missing_temperature_is_malformed(self):
        payload = _met_payload()
        del payload["properties"]["timeseries"][0]["data"]["instant"]["details"]["air_temperature"]
        provider = _provider_with_payload(payload)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"

    @pytest.mark.asyncio
    async def test_missing_timeseries_is_malformed(self):
        provider = _provider_with_payload({"properties": {}})
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"


class TestForecast:
    @pytest.mark.asyncio
    async def test_forecast_buckets_one_row_per_day(self):
        payload = _met_payload()
        # Add a second UTC day so the forecast has two buckets.
        payload["properties"]["timeseries"].append({
            "time": "2026-09-18T09:00:00Z",
            "data": {
                "instant": {"details": {"air_temperature": 31.0, "wind_speed": 6.0}},
                "next_1_hours": {"summary": {"symbol_code": "clearsky_day"}, "details": {"precipitation_amount": 0.0}},
            },
        })
        provider = _provider_with_payload(payload)
        forecast = await provider.get_forecast(19.076, 72.8777, days=2)

        assert len(forecast) == 2
        assert forecast[0].date == "2026-09-17"
        assert forecast[0].temperature_c == 29.7  # max of day temps
        assert forecast[1].date == "2026-09-18"
        assert forecast[1].temperature_c == 31.0
        assert forecast[1].condition == "Clear sky"

    @pytest.mark.asyncio
    async def test_forecast_empty_timeseries_is_malformed(self):
        provider = _provider_with_payload({"properties": {"timeseries": []}})
        with pytest.raises(WeatherProviderError):
            await provider.get_forecast(19.076, 72.8777, days=2)


class TestFailures:
    @pytest.mark.asyncio
    async def test_http_500_is_upstream_error(self):
        provider = _provider_with_payload({}, status_code=500)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_error"

    @pytest.mark.asyncio
    async def test_timeout_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        provider = MetNorwayWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_non_json_is_malformed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>nope</html>")

        provider = MetNorwayWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"


class TestHelpers:
    def test_symbol_descriptions(self):
        assert describe_symbol_code("lightrainshowers_day") == "Light rain showers"
        assert describe_symbol_code("partlycloudy_night") == "Partly cloudy"
        assert describe_symbol_code("heavyrainandthunder") == "Thunderstorm"
        assert describe_symbol_code("clearsky") == "Clear sky"
        assert describe_symbol_code(None) == "Unknown conditions"
        assert "Unknown" in describe_symbol_code("mystery_symbol")

    def test_probability_is_monotonic_and_capped(self):
        assert _derived_precip_probability(0.0) == 0.0
        assert _derived_precip_probability(None) == 0.0
        assert _derived_precip_probability(0.5) < _derived_precip_probability(2.0)
        assert _derived_precip_probability(100.0) == 95.0


class TestFactory:
    def test_factory_selects_met_norway(self, monkeypatch):
        monkeypatch.setenv("WEATHER_PROVIDER", "met_norway")
        monkeypatch.setenv("AIR_QUALITY_ENABLED", "false")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            provider = get_weather_provider()
            assert type(provider).__name__ == "ResilientWeatherProvider"
            inner = getattr(provider, "_inner", provider)
            assert type(inner).__name__ == "MetNorwayWeatherProvider"
        finally:
            get_settings.cache_clear()
            for var in ("WEATHER_PROVIDER", "AIR_QUALITY_ENABLED"):
                monkeypatch.delenv(var, raising=False)
            get_settings.cache_clear()
