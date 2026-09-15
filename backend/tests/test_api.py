"""API endpoint tests. External weather data is stubbed; no live HTTP."""
import pytest

from app.services.weather.base import WeatherProviderError

# client / stub_calm_provider fixtures now live in conftest.py and are
# shared with the chat and safety API tests.


class TestWeatherCurrentEndpoint:
    @pytest.mark.asyncio
    async def test_returns_weather_and_risk(self, client, stub_calm_provider):
        response = await client.get("/api/v1/weather/current?latitude=19.076&longitude=72.8777")
        assert response.status_code == 200
        body = response.json()
        assert body["weather"]["temperature_c"] == 29.0
        assert body["weather"]["source"] == "test"
        assert body["risk"]["level"] in ("low", "moderate", "high", "extreme")
        assert "score" in body["risk"]

    @pytest.mark.asyncio
    async def test_latitude_out_of_range_rejected(self, client, stub_calm_provider):
        response = await client.get("/api/v1/weather/current?latitude=91&longitude=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_longitude_out_of_range_rejected(self, client, stub_calm_provider):
        response = await client.get("/api/v1/weather/current?latitude=0&longitude=-181")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_params_rejected(self, client, stub_calm_provider):
        response = await client.get("/api/v1/weather/current?latitude=19.0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_coordinates_error_maps_to_422(self, client, stub_calm_provider):
        stub_calm_provider._error = WeatherProviderError("invalid_coordinates", "Bad lat")
        response = await client.get("/api/v1/weather/current?latitude=19.076&longitude=72.8777")
        assert response.status_code == 422
        assert "Bad lat" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_timeout_error_maps_to_503(self, client, stub_calm_provider):
        stub_calm_provider._error = WeatherProviderError("upstream_unavailable", "The weather service did not respond in time.")
        response = await client.get("/api/v1/weather/current?latitude=19.076&longitude=72.8777")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_upstream_error_maps_to_502_without_stack_trace(self, client, stub_calm_provider):
        stub_calm_provider._error = WeatherProviderError("upstream_error", "The weather service returned an error (HTTP 500).")
        response = await client.get("/api/v1/weather/current?latitude=19.076&longitude=72.8777")
        assert response.status_code == 502
        assert "Traceback" not in response.text


class TestForecastEndpoint:
    @pytest.mark.asyncio
    async def test_returns_forecast(self, client, stub_calm_provider):
        from app.services.weather.base import ForecastDay

        stub_calm_provider.get_forecast = lambda *a, **k: _async_forecast()
        response = await client.get("/api/v1/weather/forecast?latitude=19.076&longitude=72.8777&days=3")
        assert response.status_code == 200
        body = response.json()
        assert len(body["forecast"]) == 2
        assert body["forecast"][0]["date"] == "2026-09-09"

    @pytest.mark.asyncio
    async def test_days_out_of_bounds_rejected(self, client, stub_calm_provider):
        response = await client.get("/api/v1/weather/forecast?latitude=0&longitude=0&days=0")
        assert response.status_code == 422
        response = await client.get("/api/v1/weather/forecast?latitude=0&longitude=0&days=15")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upstream_failure_maps_to_clean_error(self, client, stub_calm_provider):
        stub_calm_provider._error = WeatherProviderError("upstream_unavailable", "Could not reach the weather service.")
        response = await client.get("/api/v1/weather/forecast?latitude=19.076&longitude=72.8777")
        assert response.status_code == 503


async def _async_forecast():
    from app.services.weather.base import ForecastDay

    return [
        ForecastDay(date="2026-09-09", rainfall_mm=5.0, temperature_c=30.0),
        ForecastDay(date="2026-09-10", rainfall_mm=1.0, temperature_c=31.0),
    ]


class TestRiskEndpoint:
    @pytest.mark.asyncio
    async def test_returns_full_assessment(self, client, stub_calm_provider):
        response = await client.get("/api/v1/risk?latitude=19.076&longitude=72.8777&role=traveler")
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "traveler"
        assert body["profile"] == "default"
        assert body["overall_severity"] in ("low", "moderate", "high", "extreme")
        assert isinstance(body["risks"], list)
        assert body["weather"]["temperature_c"] == 29.0
        assert body["assessed_at"]

    @pytest.mark.asyncio
    async def test_default_role_is_customer(self, client, stub_calm_provider):
        response = await client.get("/api/v1/risk?latitude=19.076&longitude=72.8777")
        assert response.json()["role"] == "customer"

    @pytest.mark.asyncio
    async def test_unknown_role_falls_back_to_customer(self, client, stub_calm_provider):
        response = await client.get("/api/v1/risk?latitude=19.076&longitude=72.8777&role=wizard")
        assert response.json()["role"] == "customer"

    @pytest.mark.asyncio
    async def test_all_four_roles_accepted(self, client, stub_calm_provider):
        for role in ("customer", "farmer", "traveler", "disaster_management_officer"):
            response = await client.get(f"/api/v1/risk?latitude=19.076&longitude=72.8777&role={role}")
            assert response.status_code == 200
            assert response.json()["role"] == role

    @pytest.mark.asyncio
    async def test_validation_bounds(self, client, stub_calm_provider):
        assert (await client.get("/api/v1/risk?latitude=90.1&longitude=0")).status_code == 422
        assert (await client.get("/api/v1/risk?latitude=0&longitude=180.5")).status_code == 422

    @pytest.mark.asyncio
    async def test_provider_failure_maps_cleanly(self, client, stub_calm_provider):
        stub_calm_provider._error = WeatherProviderError("malformed_response", "The weather service returned an unreadable response.")
        response = await client.get("/api/v1/risk?latitude=19.076&longitude=72.8777")
        assert response.status_code == 502
