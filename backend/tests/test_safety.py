"""Phase 4 tests: safety alerts, escalation, checklists, /safety endpoint."""
import pytest

from app.services.risk.models import RiskCategory, Severity
from app.services.safety.checklists import build_checklist
from app.services.safety.engine import SafetyEngine, alerts_from_risks
from app.services.safety.models import SafetyStatus
from app.services.safety.providers import (
    NullSafetyAlertProvider,
    get_safety_alert_provider,
    reset_safety_alert_provider,
    set_safety_alert_provider,
)


@pytest.fixture(autouse=True)
def _clean_provider():
    reset_safety_alert_provider()
    yield
    reset_safety_alert_provider()


@pytest.fixture
def storm_assessment(reading_factory, profile):
    reading = reading_factory(rainfall_mm=120.0, weather_code=95, wind_kph=45.0)
    return SafetyEngine().assess(_sync_reading(reading))


def _sync_reading(reading):
    """SafetyEngine.assess is async; build the risk assessment directly for
    synchronous alert tests."""
    from app.services.risk.engine import RiskEngine

    return RiskEngine().assess(reading)


class TestEscalationMapping:
    def test_severity_to_status_mapping(self):
        assert SafetyStatus.from_severity("low") is SafetyStatus.NORMAL
        assert SafetyStatus.from_severity("moderate") is SafetyStatus.WATCH
        assert SafetyStatus.from_severity("high") is SafetyStatus.WARNING
        assert SafetyStatus.from_severity("extreme") is SafetyStatus.CRITICAL

    def test_unknown_severity_defaults_to_normal(self):
        assert SafetyStatus.from_severity("bogus") is SafetyStatus.NORMAL

    def test_status_ranking(self):
        assert SafetyStatus.CRITICAL.rank > SafetyStatus.WARNING.rank > SafetyStatus.WATCH.rank > SafetyStatus.NORMAL.rank


class TestAlertGeneration:
    def test_moderate_plus_risks_become_alerts(self, reading_factory, profile):
        assessment = _sync_reading(reading_factory(rainfall_mm=70.0))
        alerts = alerts_from_risks(assessment)
        assert alerts
        assert all(alert.severity in ("moderate", "high", "extreme") for alert in alerts)
        assert all(alert.source == "weathergpt_risk_engine" for alert in alerts)
        assert all(alert.is_official is False for alert in alerts)

    def test_low_risks_do_not_become_alerts(self, reading_factory):
        assessment = _sync_reading(reading_factory())  # calm conditions
        assert alerts_from_risks(assessment) == []

    def test_alert_ids_deterministic_for_dedup(self, reading_factory):
        a1 = alerts_from_risks(_sync_reading(reading_factory(rainfall_mm=70.0)))
        a2 = alerts_from_risks(_sync_reading(reading_factory(rainfall_mm=75.0)))
        ids1 = {a.id for a in a1}
        ids2 = {a.id for a in a2}
        assert ids1 == ids2  # same category+severity+location => same ids

    def test_alerts_carry_action_and_explanation(self, reading_factory):
        alerts = alerts_from_risks(_sync_reading(reading_factory(rainfall_mm=70.0)))
        assert all(a.recommended_action for a in alerts)
        assert all(a.explanation for a in alerts)
        assert all(a.timestamp for a in alerts)


class TestChecklists:
    def test_calm_conditions_yield_only_preparedness(self, reading_factory, profile):
        assessment = _sync_reading(reading_factory())
        items = build_checklist(assessment.risks, "customer")
        assert items  # preparedness items always present
        assert all(category == "preparedness" for _, category in items)

    def test_rain_activates_rain_items(self, reading_factory, profile):
        assessment = _sync_reading(reading_factory(rainfall_mm=70.0))
        items = build_checklist(assessment.risks, "customer")
        categories = {c for _, c in items}
        assert "rainfall" in categories

    def test_heat_activates_heat_items(self, reading_factory, profile):
        assessment = _sync_reading(reading_factory(temperature_c=42.0, apparent_temperature_c=44.0))
        categories = {c for _, c in build_checklist(assessment.risks, "farmer")}
        assert "high_temperature" in categories or "heat_stress" in categories

    def test_roles_cap_item_counts(self, reading_factory, profile):
        storm = reading_factory(rainfall_mm=150.0, weather_code=95, wind_kph=100.0, temperature_c=48.0, apparent_temperature_c=50.0)
        assessment = _sync_reading(storm)
        officer_items = build_checklist(assessment.risks, "disaster_management_officer")
        customer_items = build_checklist(assessment.risks, "customer")
        assert len([i for i in officer_items if i[1] != "preparedness"]) >= len([i for i in customer_items if i[1] != "preparedness"])


class TestOfficialAlertProvider:
    @pytest.mark.asyncio
    async def test_null_provider_returns_no_official_alerts(self, reading_factory):
        engine = SafetyEngine()
        result = await engine.assess(reading_factory(), role="customer")
        assert result.official_alerts == []
        assert get_safety_alert_provider().name == "null"

    @pytest.mark.asyncio
    async def test_official_provider_can_escalate_status(self, reading_factory):
        from app.services.safety.models import SafetyAlert

        class FakeOfficialProvider(NullSafetyAlertProvider):
            name = "fake_official"

            async def get_alerts(self, latitude, longitude):
                return [
                    SafetyAlert(
                        id="official_1",
                        category="severe_weather",
                        severity="extreme",
                        title="Official Test Alert",
                        explanation="Issued by a real authority (test double).",
                        recommended_action="Follow official instructions.",
                        timestamp="2026-09-09T00:00:00+00:00",
                        latitude=latitude,
                        longitude=longitude,
                        source="test_authority",
                        is_official=True,
                    )
                ]

        set_safety_alert_provider(FakeOfficialProvider())
        engine = SafetyEngine()
        result = await engine.assess(reading_factory(), role="customer")  # calm weather
        # Calm weather would be NORMAL, but the official EXTREME alert escalates.
        assert result.status == "critical"
        assert result.official_alerts[0].is_official is True

    @pytest.mark.asyncio
    async def test_provider_failure_does_not_break_safety(self, reading_factory):
        class BrokenProvider(NullSafetyAlertProvider):
            async def get_alerts(self, latitude, longitude):
                raise RuntimeError("feed down")

        set_safety_alert_provider(BrokenProvider())
        engine = SafetyEngine()
        result = await engine.assess(reading_factory(rainfall_mm=70.0), role="customer")
        assert result.status in ("normal", "watch", "warning", "critical")  # still returns a status
        assert result.official_alerts == []


class TestSafetyEndpoint:
    @pytest.mark.asyncio
    async def test_returns_full_safety_assessment(self, client, stub_calm_provider):
        response = await client.get("/api/v1/safety?latitude=19.076&longitude=72.8777&role=farmer")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("normal", "watch", "warning", "critical")
        assert body["role"] == "farmer"
        assert isinstance(body["alerts"], list)
        assert body["checklist"]
        assert "NOT an official government warning" in body["disclaimer"]
        assert body["weather_is_verified"] is False

    @pytest.mark.asyncio
    async def test_storm_scenario_yields_alerts(self, client, stub_calm_provider):
        from app.services.weather.base import WeatherReading

        stub_calm_provider._reading = WeatherReading(
            location_label="19.076, 72.878",
            latitude=19.076,
            longitude=72.8777,
            observed_at="2026-09-09T06:00",
            temperature_c=25.0,
            condition="Heavy rain",
            rainfall_mm=120.0,
            precip_probability_pct=97.0,
            humidity_pct=91.0,
            wind_kph=45.0,
            source="test",
            is_verified=False,
            weather_code=95,
        )
        response = await client.get("/api/v1/safety?latitude=19.076&longitude=72.8777")
        body = response.json()
        assert body["status"] in ("warning", "critical")
        assert body["alerts"]
        assert any(a["category"] in ("rainfall", "flood_potential", "severe_weather") for a in body["alerts"])

    @pytest.mark.asyncio
    async def test_validation_bounds(self, client, stub_calm_provider):
        assert (await client.get("/api/v1/safety?latitude=95&longitude=0")).status_code == 422
        assert (await client.get("/api/v1/safety?latitude=0&longitude=-999")).status_code == 422

    @pytest.mark.asyncio
    async def test_provider_failure_maps_cleanly(self, client, stub_calm_provider):
        from app.services.weather.base import WeatherProviderError

        stub_calm_provider._error = WeatherProviderError("upstream_unavailable", "The weather service did not respond in time.")
        response = await client.get("/api/v1/safety?latitude=19.076&longitude=72.8777")
        assert response.status_code == 503


class TestSafetyEventModel:
    def test_safety_event_table_exists(self):
        from app.models.models import SafetyEvent

        columns = {c.name for c in SafetyEvent.__table__.columns}
        assert {"event_type", "severity", "latitude", "longitude", "status", "source", "detected_at"} <= columns
