"""Open-Meteo air-quality + geocoding service tests. All HTTP is mocked; nothing hits the live API."""
import httpx
import pytest

from app.services.weather.air_quality import (
    AirQualityProviderError,
    OpenMeteoAirQualityProvider,
    us_aqi_band,
)
from app.services.weather.geocoding import GeoCodingError, OpenMeteoGeoCoder


def _aqi_payload(**overrides):
    payload = {
        "latitude": 19.076,
        "longitude": 72.8777,
        "current": {
            "time": "2026-09-09T06:00",
            "us_aqi": 168.0,
            "pm2_5": 75.6,
            "pm10": 126.0,
        },
    }
    payload.update(overrides)
    return payload


def _aqi_provider_with(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return OpenMeteoAirQualityProvider(transport=httpx.MockTransport(handler))


def _geo_provider_with(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return OpenMeteoGeoCoder(transport=httpx.MockTransport(handler))


class TestUsAqiBands:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "Good"),
            (50, "Good"),
            (50.1, "Moderate"),
            (100, "Moderate"),
            (100.1, "Unhealthy for sensitive groups"),
            (150, "Unhealthy for sensitive groups"),
            (150.1, "Unhealthy"),
            (200, "Unhealthy"),
            (200.1, "Very unhealthy"),
            (300, "Very unhealthy"),
            (300.1, "Hazardous"),
            (500, "Hazardous"),
        ],
    )
    def test_band_boundaries(self, value, expected):
        assert us_aqi_band(value) == expected


class TestAirQualityProvider:
    @pytest.mark.asyncio
    async def test_maps_all_fields(self):
        provider = _aqi_provider_with(_aqi_payload())
        aqi = await provider.get_current(19.076, 72.8777)

        assert aqi.us_aqi == 168.0
        assert aqi.pm2_5 == 75.6
        assert aqi.pm10 == 126.0
        assert aqi.band == "Unhealthy"
        assert aqi.observed_at == "2026-09-09T06:00"
        assert aqi.source == "open-meteo-air-quality"
        assert aqi.is_verified is True

    @pytest.mark.asyncio
    async def test_missing_optional_pollutants_become_none(self):
        payload = _aqi_payload()
        del payload["current"]["pm2_5"]
        del payload["current"]["pm10"]
        provider = _aqi_provider_with(payload)
        aqi = await provider.get_current(19.076, 72.8777)
        assert aqi.pm2_5 is None
        assert aqi.pm10 is None
        assert aqi.us_aqi == 168.0

    @pytest.mark.asyncio
    async def test_missing_aqi_is_no_data_not_error_payload(self):
        """Coverage gaps mean 'no data' — enrichment skips, weather survives."""
        payload = _aqi_payload()
        payload["current"]["us_aqi"] = None
        provider = _aqi_provider_with(payload)
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "no_data"

    @pytest.mark.asyncio
    async def test_missing_current_section_is_malformed(self):
        payload = _aqi_payload()
        del payload["current"]
        provider = _aqi_provider_with(payload)
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"

    @pytest.mark.asyncio
    async def test_http_500_is_upstream_error(self):
        provider = _aqi_provider_with({}, status_code=500)
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_error"

    @pytest.mark.asyncio
    async def test_timeout_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        provider = OpenMeteoAirQualityProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_connection_failure_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = OpenMeteoAirQualityProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_non_json_body_is_malformed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>not json</html>")

        provider = OpenMeteoAirQualityProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(AirQualityProviderError) as excinfo:
            await provider.get_current(19.076, 72.8777)
        assert excinfo.value.kind == "malformed_response"


class TestGeoCoding:
    @pytest.mark.asyncio
    async def test_search_maps_results(self):
        payload = {
            "results": [
                {
                    "name": "Mumbai",
                    "latitude": 19.076,
                    "longitude": 72.8777,
                    "country": "India",
                    "admin1": "Maharashtra",
                    "timezone": "Asia/Kolkata",
                },
                {"name": "Mumbai Suburban", "latitude": 19.13, "longitude": 72.85, "country": "India"},
            ]
        }
        coder = _geo_provider_with(payload)
        places = await coder.search("Mumbai")

        assert len(places) == 2
        assert places[0].name == "Mumbai"
        assert places[0].latitude == 19.076
        assert places[0].label == "Mumbai, Maharashtra, India"
        assert places[0].timezone == "Asia/Kolkata"
        assert places[1].admin1 is None
        assert places[1].label == "Mumbai Suburban, India"

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_list_without_http(self):
        coder = _geo_provider_with({"results": []})
        assert await coder.search("   ") == []

    @pytest.mark.asyncio
    async def test_no_matches_is_empty_result_not_error(self):
        coder = _geo_provider_with({"generationtime_ms": 1.2})  # no `results` key
        places = await coder.search("nowhere-xyz-123")
        assert places == []

    @pytest.mark.asyncio
    async def test_malformed_entries_are_skipped(self):
        payload = {
            "results": [
                {"name": "Ok Place", "latitude": 10.0, "longitude": 20.0},
                {"latitude": 30.0, "longitude": 40.0},  # no name
                {"name": "No Coords"},
                "not-a-dict",
            ]
        }
        coder = _geo_provider_with(payload)
        places = await coder.search("mixed")
        assert len(places) == 1
        assert places[0].name == "Ok Place"

    @pytest.mark.asyncio
    async def test_http_500_is_upstream_error(self):
        coder = _geo_provider_with({}, status_code=500)
        with pytest.raises(GeoCodingError) as excinfo:
            await coder.search("Mumbai")
        assert excinfo.value.kind == "upstream_error"

    @pytest.mark.asyncio
    async def test_timeout_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        coder = OpenMeteoGeoCoder(transport=httpx.MockTransport(handler))
        with pytest.raises(GeoCodingError) as excinfo:
            await coder.search("Mumbai")
        assert excinfo.value.kind == "upstream_unavailable"

    @pytest.mark.asyncio
    async def test_non_dict_json_is_malformed(self):
        coder = _geo_provider_with(["unexpected"])
        with pytest.raises(GeoCodingError) as excinfo:
            await coder.search("Mumbai")
        assert excinfo.value.kind == "malformed_response"


class TestGeoEndpoint:
    @pytest.mark.asyncio
    async def test_search_returns_places(self, client, monkeypatch):
        from app.api.v1.routers import geo as geo_router

        class StubCoder:
            async def search(self, query, count=5):
                from app.services.weather.geocoding import GeoPlace

                return [GeoPlace(name="Mumbai", latitude=19.076, longitude=72.8777, country="India", admin1="Maharashtra")]

        monkeypatch.setattr(geo_router, "OpenMeteoGeoCoder", lambda: StubCoder())
        response = await client.get("/api/v1/geo/search?query=Mumbai")
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "Mumbai"
        assert body["results"][0]["label"] == "Mumbai, Maharashtra, India"
        assert body["results"][0]["latitude"] == 19.076

    @pytest.mark.asyncio
    async def test_unknown_place_is_empty_200(self, client, monkeypatch):
        from app.api.v1.routers import geo as geo_router

        class StubCoder:
            async def search(self, query, count=5):
                return []

        monkeypatch.setattr(geo_router, "OpenMeteoGeoCoder", lambda: StubCoder())
        response = await client.get("/api/v1/geo/search?query=zzz-not-a-place")
        assert response.status_code == 200
        assert response.json()["results"] == []

    @pytest.mark.asyncio
    async def test_missing_query_rejected(self, client):
        assert (await client.get("/api/v1/geo/search")).status_code == 422

    @pytest.mark.asyncio
    async def test_count_out_of_bounds_rejected(self, client):
        assert (await client.get("/api/v1/geo/search?query=x&count=11")).status_code == 422
        assert (await client.get("/api/v1/geo/search?query=x&count=0")).status_code == 422

    @pytest.mark.asyncio
    async def test_upstream_failure_maps_to_503(self, client, monkeypatch):
        from app.api.v1.routers import geo as geo_router
        from app.services.weather.geocoding import GeoCodingError

        class StubCoder:
            async def search(self, query, count=5):
                raise GeoCodingError("upstream_unavailable", "The location service did not respond in time.")

        monkeypatch.setattr(geo_router, "OpenMeteoGeoCoder", lambda: StubCoder())
        response = await client.get("/api/v1/geo/search?query=Mumbai")
        assert response.status_code == 503
        assert "location service" in response.json()["detail"]
