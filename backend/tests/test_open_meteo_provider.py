"""Open-Meteo provider tests. All HTTP is mocked; nothing hits the live API."""
import json

import httpx
import pytest

from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider
from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.services.weather.wmo_codes import describe_wmo_code, describe_wmo_code_short


def _open_meteo_payload(**overrides):
    """A realistic Open-Meteo response (current + hourly + daily)."""
    payload = {
        "latitude": 19.076,
        "longitude": 72.8777,
        "current": {
            "time": "2026-09-09T06:00",
            "temperature_2m": 25.5,
            "apparent_temperature": 31.3,
            "relative_humidity_2m": 84,
            "precipitation": 0.4,
            "weather_code": 95,
        },
        "hourly": {
            "time": ["2026-09-09T05:00", "2026-09-09T06:00", "2026-09-09T07:00"],
            "temperature_2m": [25.0, 25.5, 26.0],
            "apparent_temperature": [30.0, 31.3, 32.0],
            "relative_humidity_2m": [86, 84, 83],
            "precipitation": [0.0, 0.4, 0.6],
            "precipitation_probability": [20, 65, 80],
            "wind_speed_10m": [8.1, 12.4, 15.0],
            "wind_direction_10m": [270, 315, 22],
            "wind_gusts_10m": [14.2, 19.8, 24.0],
            "weather_code": [2, 95, 95],
        },
        "daily": {
            "time": ["2026-09-09", "2026-09-10"],
            "weather_code": [95, 61],
            "temperature_2m_max": [29.0, 30.1],
            "apparent_temperature_max": [33.0, 34.2],
            "precipitation_sum": [18.2, 40.0],
            "precipitation_probability_max": [88, 91],
            "wind_speed_10m_max": [22.5, 44.0],
        },
    }
    payload.update(overrides)
    return payload


def _provider_with_payload(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))


class TestFactory:
    def test_factory_selects_open_meteo(self, monkeypatch):
        monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            provider = get_weather_provider()
            assert type(provider).__name__ == "OpenMeteoWeatherProvider"
        finally:
            get_settings.cache_clear()
            monkeypatch.delenv("WEATHER_PROVIDER", raising=False)
            get_settings.cache_clear()

    def test_factory_selects_mock(self, monkeypatch):
        monkeypatch.setenv("WEATHER_PROVIDER", "mock")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            provider = get_weather_provider()
            assert type(provider).__name__ == "MockWeatherProvider"
        finally:
            get_settings.cache_clear()
            monkeypatch.delenv("WEATHER_PROVIDER", raising=False)
            get_settings.cache_clear()

    def test_factory_rejects_unknown(self, monkeypatch):
        monkeypatch.setenv("WEATHER_PROVIDER", "nonexistent_provider")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            with pytest.raises(ValueError):
                get_weather_provider()
        finally:
            get_settings.cache_clear()
            monkeypatch.delenv("WEATHER_PROVIDER", raising=False)
            get_settings.cache_clear()


class TestCurrentMapping:
    @pytest.mark.asyncio
    async def test_current_maps_all_fields(self):
        provider = _provider_with_payload(_open_meteo_payload())
        reading = await provider.get_current(19.076, 72.8777)

        assert reading.temperature_c == 25.5
        assert reading.apparent_temperature_c == 31.3
        assert reading.rainfall_mm == 0.4
        assert reading.precip_probability_pct == 65.0  # matched by hour index
        assert reading.humidity_pct == 84.0
        assert reading.wind_kph == 12.4
        assert reading.wind_gust_kph == 19.8
        assert reading.weather_code == 95
        assert reading.condition == "Thunderstorm"
        assert reading.source == "open-meteo"
        assert reading.is_verified is True
        assert reading.observed_at == "2026-09-09T06:00"

    @pytest.mark.asyncio
    async def test_current_wind_direction_converted_to_compass(self):
        provider = _provider_with_payload(_open_meteo_payload())
        reading = await provider.get_current(19.076, 72.8777)
        assert reading.wind_direction_deg == 315.0
        assert reading.wind_direction == "NW"

    @pytest.mark.asyncio
    async def test_missing_optional_hourly_fields_do_not_crash(self):
        payload = _open_meteo_payload()
        for key in ["wind_direction_10m", "wind_gusts_10m", "precipitation_probability"]:
            payload["hourly"][key] = [None, None, None]
        provider = _provider_with_payload(payload)
        reading = await provider.get_current(19.076, 72.8777)
        assert reading.wind_direction is None
        assert reading.wind_gust_kph is None
        assert reading.precip_probability_pct == 0.0

    @pytest.mark.asyncio
    async def test_missing_required_field_is_malformed(self):
        payload = _open_meteo_payload()
        del payload["current"]["temperature_2m"]
        provider = _provider_with_payload(payload)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"

    @pytest.mark.asyncio
    async def test_missing_current_section_is_malformed(self):
        payload = _open_meteo_payload()
        del payload["current"]
        provider = _provider_with_payload(payload)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"


class TestForecastMapping:
    @pytest.mark.asyncio
    async def test_forecast_maps_days(self):
        provider = _provider_with_payload(_open_meteo_payload())
        forecast = await provider.get_forecast(19.076, 72.8777, days=2)

        assert len(forecast) == 2
        assert forecast[0].date == "2026-09-09"
        assert forecast[0].temperature_c == 29.0
        assert forecast[0].rainfall_mm == 18.2
        assert forecast[0].precipitation_probability_pct == 88.0
        assert forecast[0].condition == "Thunderstorm"
        assert forecast[1].condition == "Light rain"  # WMO code 61

    @pytest.mark.asyncio
    async def test_forecast_without_daily_is_malformed(self):
        payload = _open_meteo_payload()
        del payload["daily"]
        provider = _provider_with_payload(payload)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_forecast(19.076, 72.8777, days=2)
        assert excinfo.value.kind == "malformed_response"


class TestWeatherCodeMapping:
    def test_known_codes(self):
        assert describe_wmo_code(0) == "Clear sky"
        assert describe_wmo_code(65) == "Heavy rain"
        assert describe_wmo_code(95) == "Thunderstorm"
        assert describe_wmo_code_short(61) == "Light rain"

    def test_unknown_and_missing_codes(self):
        assert "Unrecognized" in describe_wmo_code(123)
        assert describe_wmo_code(None) == "Unknown conditions"
        assert describe_wmo_code_short(None) == "Unknown"

    def test_wind_direction_compass(self):
        from app.services.weather.base import wind_direction_to_compass

        assert wind_direction_to_compass(0) == "N"
        assert wind_direction_to_compass(90) == "E"
        assert wind_direction_to_compass(315) == "NW"
        assert wind_direction_to_compass(361) == "N"  # wraps


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_http_400_is_invalid_coordinates(self):
        provider = _provider_with_payload({"error": True, "reason": "Invalid latitude"}, status_code=400)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(999.0, 72.8777)
        assert excinfo.value.kind == "invalid_coordinates"

    @pytest.mark.asyncio
    async def test_http_500_is_upstream_error(self):
        provider = _provider_with_payload({}, status_code=500)
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_error"

    @pytest.mark.asyncio
    async def test_soft_error_in_200_body_is_surfaced(self):
        provider = _provider_with_payload({"error": True, "reason": "Out of range coordinates"})
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "invalid_coordinates"

    @pytest.mark.asyncio
    async def test_timeout_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        provider = OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_connection_failure_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_non_json_body_is_malformed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>not json</html>")

        provider = OpenMeteoWeatherProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"

    @pytest.mark.asyncio
    async def test_non_dict_json_is_malformed(self):
        provider = _provider_with_payload(["unexpected", "list"])
        with pytest.raises(WeatherProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"
