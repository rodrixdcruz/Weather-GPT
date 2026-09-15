"""AIR_QUALITY risk detector tests: threshold boundaries, no-data silence, scoring, roles, and API flow."""
import pytest

from app.services.risk.air_quality_detector import detect_air_quality
from app.services.risk.engine import RiskEngine
from app.services.risk.models import RiskCategory, Severity
from app.services.weather.air_quality import AirQuality
from app.services.weather.base import WeatherReading


def _reading_with_aqi(us_aqi, **reading_overrides):
    base = dict(
        location_label="19.076, 72.878",
        latitude=19.076,
        longitude=72.8777,
        observed_at="2026-09-09T06:00",
        temperature_c=29.0,
        condition="Hazy smog",
        rainfall_mm=2.0,
        precip_probability_pct=10.0,
        humidity_pct=55.0,
        wind_kph=12.0,
        source="test",
        is_verified=False,
        air_quality=AirQuality(observed_at="2026-09-09T06:00", us_aqi=us_aqi),
    )
    base.update(reading_overrides)
    return WeatherReading(**base)


class TestAirQualityDetectorBoundaries:
    """Exact US-AQI profile thresholds: 51 / 101 / 151."""

    @pytest.mark.parametrize(
        "us_aqi,expected",
        [
            (50.9, None),
            (51.0, Severity.MODERATE),
            (100.9, Severity.MODERATE),
            (101.0, Severity.HIGH),
            (150.9, Severity.HIGH),
            (151.0, Severity.EXTREME),
            (168.0, Severity.EXTREME),
            (350.0, Severity.EXTREME),
        ],
    )
    def test_boundary_mapping(self, profile, role, us_aqi, expected):
        risks = detect_air_quality(_reading_with_aqi(us_aqi), profile, role)
        if expected is None:
            assert risks == []
        else:
            assert len(risks) == 1
            assert risks[0].severity == expected

    def test_no_air_quality_data_is_silent(self, profile, role, reading_factory):
        """The core honesty rule: no AQI data -> no fabricated AQI risk."""
        reading = reading_factory()  # air_quality=None
        assert detect_air_quality(reading, profile, role) == []
        assert RiskEngine(profile).assess(reading).risks == [] or all(
            r.category != RiskCategory.AIR_QUALITY for r in RiskEngine(profile).assess(reading).risks
        )

    def test_detection_context_fields(self, profile, role):
        risks = detect_air_quality(_reading_with_aqi(168.0), profile, role)
        item = risks[0]
        assert item.category == RiskCategory.AIR_QUALITY
        assert item.affected_metric == "us_aqi"
        assert item.measured_value == 168.0
        assert item.guidance and isinstance(item.guidance[0], str)
        assert "168" in item.explanation

    def test_score_is_band_consistent(self, profile, role):
        """Score stays within the EXTREME band (75-100) at 168 AQI."""
        risks = detect_air_quality(_reading_with_aqi(168.0), profile, role)
        assert 75.0 <= risks[0].score <= 100.0

    def test_score_deepens_within_band(self, profile, role):
        """Depth drives the score inside a band (HIGH: 101-150), matching
        the shared scoring convention; EXTREME clamps at the 100 cap."""
        low_high = detect_air_quality(_reading_with_aqi(102.0), profile, role)[0].score
        deep_high = detect_air_quality(_reading_with_aqi(149.0), profile, role)[0].score
        assert deep_high > low_high
        assert detect_air_quality(_reading_with_aqi(300.0), profile, role)[0].score == 100.0


class TestAirQualityInEngine:
    def test_engine_surfaces_air_quality_risk(self, profile, role):
        assessment = RiskEngine(profile).assess(_reading_with_aqi(168.0))
        categories = {r.category for r in assessment.risks}
        assert RiskCategory.AIR_QUALITY in categories

    def test_engine_sorts_air_quality_by_role(self, profile):
        """With two competing risks (smog AQI 168 + 43°C heat), customer puts
        air_quality first while farmer puts temperature first — ordering
        changes per role, measurements do not."""
        reading = _reading_with_aqi(168.0, temperature_c=43.0)
        customer = RiskEngine(profile).assess(reading, role="customer")
        farmer = RiskEngine(profile).assess(reading, role="farmer")
        assert customer.risks[0].category == RiskCategory.AIR_QUALITY
        # Farmer priority: heat_stress (apparent-temp fallback at 43°C) first.
        assert farmer.risks[0].category == RiskCategory.HEAT_STRESS
        # Same measurements regardless of role:
        assert len(customer.risks) == len(farmer.risks)

    def test_no_aqi_reading_produces_no_air_quality_risk(self, profile, reading_factory):
        assessment = RiskEngine(profile).assess(reading_factory())
        assert all(r.category != RiskCategory.AIR_QUALITY for r in assessment.risks)


class TestAirQualityMockProvider:
    @pytest.mark.asyncio
    async def test_mock_ships_scenario_aqi(self):
        from app.services.weather.mock_provider import MockWeatherProvider

        reading = await MockWeatherProvider(scenario="smog").get_current(19.076, 72.8777)
        assert reading.air_quality is not None
        assert reading.air_quality.us_aqi == 168.0
        assert reading.air_quality.is_verified is False

    @pytest.mark.asyncio
    async def test_mock_normal_scenario_is_good_aqi(self):
        from app.services.weather.mock_provider import MockWeatherProvider

        reading = await MockWeatherProvider(scenario="normal").get_current(19.076, 72.8777)
        assert reading.air_quality.us_aqi == 42.0


class TestAirQualityEndpointFlow:
    @pytest.mark.asyncio
    async def test_aqi_flows_through_weather_api(self, client, stub_calm_provider):
        """The conftest stub returns the calm reading (no AQI) — endpoint must
        serialize cleanly with air_quality=None."""
        response = await client.get("/api/v1/weather/current?latitude=19.076&longitude=72.8777")
        assert response.status_code == 200
        assert response.json()["weather"]["air_quality"] is None

    @pytest.mark.asyncio
    async def test_aqi_flows_through_mock_scenario_api(self, client, monkeypatch):
        """With the real mock provider, the smog scenario surfaces the AQI risk end-to-end."""
        from app.api.v1.routers import risk as risk_router
        from app.api.v1.routers import weather as weather_router
        from app.services.weather.factory import get_weather_provider as _real

        # Route through the actual mock provider for this test only.
        monkeypatch.setattr(weather_router, "get_weather_provider", lambda scenario="normal": _real(scenario))
        monkeypatch.setattr(risk_router, "get_weather_provider", lambda scenario="normal": _real(scenario))

        response = await client.get("/api/v1/risk?latitude=19.076&longitude=72.8777&role=customer&scenario=smog")
        assert response.status_code == 200
        body = response.json()
        categories = {r["category"] for r in body["risks"]}
        assert "air_quality" in categories
        aqi_risk = next(r for r in body["risks"] if r["category"] == "air_quality")
        assert aqi_risk["severity"] == "extreme"
        assert aqi_risk["measured_value"] == 168.0
        assert body["weather"]["air_quality"]["us_aqi"] == 168.0
        assert body["weather"]["air_quality"]["is_verified"] is False
