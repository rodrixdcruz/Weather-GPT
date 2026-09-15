"""Risk engine orchestration and role-overlay tests."""
import pytest

from app.services.risk.engine import RiskEngine
from app.services.risk.models import Severity
from app.services.risk.roles import (
    CUSTOMER,
    DISASTER_MANAGEMENT_OFFICER,
    FARMER,
    KNOWN_ROLES,
    TRAVELER,
    normalize_role,
    sort_risks_for_role,
)


class TestRoleNormalization:
    def test_default_role_is_customer(self):
        assert normalize_role(None) == CUSTOMER
        assert normalize_role("") == CUSTOMER
        assert normalize_role("  ") == CUSTOMER

    def test_case_and_separator_variants(self):
        assert normalize_role("FARMER") == FARMER
        assert normalize_role("disaster-management-officer") == DISASTER_MANAGEMENT_OFFICER
        assert normalize_role("Disaster Management Officer") == DISASTER_MANAGEMENT_OFFICER

    def test_unknown_falls_back_to_customer(self):
        assert normalize_role("admin") == CUSTOMER


class TestEngineAssessment:
    def test_healthy_conditions_produce_no_risks(self, reading_factory, profile):
        assessment = RiskEngine(profile).assess(reading_factory())
        assert assessment.risks == []
        assert assessment.overall_severity is Severity.LOW
        assert assessment.overall_score == 0.0

    def test_assessment_carries_provenance(self, reading_factory, profile):
        reading = reading_factory(source="open-meteo", is_verified=True)
        assessment = RiskEngine(profile).assess(reading)
        assert assessment.weather_source == "open-meteo"
        assert assessment.weather_is_verified is True
        assert assessment.assessed_at  # ISO timestamp present
        assert assessment.profile == "default"

    def test_all_eight_detectors_can_fire(self, reading_factory, profile):
        storm = reading_factory(
            rainfall_mm=150.0,
            temperature_c=48.0,
            apparent_temperature_c=50.0,
            wind_kph=100.0,
            weather_code=99,
        )
        risks = RiskEngine(profile).assess(storm).risks
        categories = {r.category for r in risks}
        assert RiskCategory.RAINFALL in categories
        assert RiskCategory.HIGH_TEMPERATURE in categories
        assert RiskCategory.HEAT_STRESS in categories
        assert RiskCategory.STRONG_WIND in categories
        assert RiskCategory.SEVERE_WEATHER in categories
        assert RiskCategory.FLOOD_POTENTIAL in categories
        assert RiskCategory.POOR_TRAVEL_CONDITIONS in categories
        assert RiskCategory.ACTIVITY_DISRUPTION in categories


from app.services.risk.models import RiskCategory  # noqa: E402  (used above)


class TestRoleOverlay:
    @pytest.fixture
    def mixed_risks(self, reading_factory, profile):
        reading = reading_factory(rainfall_mm=70.0, weather_code=95, temperature_c=34.0, apparent_temperature_c=36.0, wind_kph=45.0)
        return RiskEngine(profile).assess(reading).risks

    def test_roles_only_reorder(self, reading_factory, profile, mixed_risks):
        """Role overlay must NOT change the set of risks or their content."""
        by_role = {
            role: RiskEngine(profile).assess(reading_factory(rainfall_mm=70.0, weather_code=95), role=role).risks
            for role in KNOWN_ROLES
        }
        sets = {role: {(r.category, r.severity, r.score) for r in risks} for role, risks in by_role.items()}
        assert len({frozenset(s) for s in sets.values()}) == 1  # same risks everywhere

    def test_farmer_prioritizes_rainfall(self, reading_factory, profile):
        reading = reading_factory(rainfall_mm=70.0, weather_code=95)
        risks = RiskEngine(profile).assess(reading, role=FARMER).risks
        assert risks[0].category is RiskCategory.RAINFALL

    def test_traveler_prioritizes_travel_conditions(self, reading_factory, profile):
        reading = reading_factory(rainfall_mm=70.0, weather_code=95)
        risks = RiskEngine(profile).assess(reading, role=TRAVELER).risks
        assert risks[0].category is RiskCategory.POOR_TRAVEL_CONDITIONS

    def test_officer_prioritizes_severe_weather(self, reading_factory, profile):
        reading = reading_factory(rainfall_mm=70.0, weather_code=95)
        risks = RiskEngine(profile).assess(reading, role=DISASTER_MANAGEMENT_OFFICER).risks
        assert risks[0].category is RiskCategory.SEVERE_WEATHER

    def test_guidance_differs_by_role(self, reading_factory, profile):
        reading = reading_factory(rainfall_mm=70.0)
        farmer_guidance = RiskEngine(profile).assess(reading, role=FARMER).risks[0].guidance
        traveler_guidance = RiskEngine(profile).assess(reading, role=TRAVELER).risks[0].guidance
        assert farmer_guidance != traveler_guidance

    def test_every_role_yields_sorted_output(self, mixed_risks, profile):
        for role in KNOWN_ROLES:
            ordered = sort_risks_for_role(mixed_risks, profile, role)
            priorities = profile.role_priorities[role]
            indexes = [priorities.index(r.category.value) for r in ordered]
            assert indexes == sorted(indexes)


class TestForecastRisks:
    def test_forecast_risks_carry_affected_day(self, profile):
        from app.services.weather.base import ForecastDay

        forecast = [ForecastDay(date="2026-09-12", rainfall_mm=120.0, temperature_c=30.0, precipitation_probability_pct=90.0)]
        risks = RiskEngine(profile).assess_forecast_only(forecast, role=CUSTOMER)
        assert risks
        assert all(r.affected_day == "2026-09-12" for r in risks)
        assert any(r.category is RiskCategory.RAINFALL for r in risks)

    def test_assess_accepts_forecast(self, reading_factory, profile):
        from app.services.weather.base import ForecastDay

        forecast = [ForecastDay(date="2026-09-12", rainfall_mm=130.0, temperature_c=31.0)]
        assessment = RiskEngine(profile).assess(reading_factory(), forecast=forecast)
        assert any(r.affected_day == "2026-09-12" for r in assessment.risks)
