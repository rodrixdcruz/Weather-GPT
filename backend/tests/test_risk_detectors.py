"""Risk detector tests: threshold bands, composite risks, and profile config."""
import pytest

from app.services.risk.detectors import (
    detect_activity_disruption,
    detect_flood_potential,
    detect_heat_stress,
    detect_high_temperature,
    detect_poor_travel_conditions,
    detect_rainfall,
    detect_severe_weather,
    detect_strong_wind,
)
from app.services.risk.models import RiskCategory, Severity


class TestRainfallThresholds:
    """Baseline: MODERATE >= 35.6 mm, HIGH >= 64.5, EXTREME >= 115.6 (IMD)."""

    def test_below_moderate_not_detected(self, reading_factory, profile):
        risks = detect_rainfall(reading_factory(rainfall_mm=35.5), profile, "customer")
        assert risks == []

    def test_moderate_band(self, reading_factory, profile):
        risk = detect_rainfall(reading_factory(rainfall_mm=35.6), profile, "customer")[0]
        assert risk.severity is Severity.MODERATE
        assert risk.category is RiskCategory.RAINFALL
        assert 20 <= risk.score < 45

    def test_high_band(self, reading_factory, profile):
        risk = detect_rainfall(reading_factory(rainfall_mm=64.5), profile, "customer")[0]
        assert risk.severity is Severity.HIGH
        assert 45 <= risk.score < 75

    def test_extreme_band(self, reading_factory, profile):
        risk = detect_rainfall(reading_factory(rainfall_mm=115.6), profile, "customer")[0]
        assert risk.severity is Severity.EXTREME
        assert risk.score >= 75

    def test_explanation_mentions_measurement_and_threshold(self, reading_factory, profile):
        risk = detect_rainfall(reading_factory(rainfall_mm=70), profile, "customer")[0]
        assert "70 mm" in risk.explanation
        assert "64.5" in risk.explanation


class TestHighTemperature:
    """Baseline: MODERATE >= 32C, HIGH >= 40C, EXTREME >= 46C."""

    def test_below_moderate_not_detected(self, reading_factory, profile):
        assert detect_high_temperature(reading_factory(temperature_c=31.9), profile, "customer") == []

    def test_moderate_band(self, reading_factory, profile):
        risk = detect_high_temperature(reading_factory(temperature_c=32.0), profile, "customer")[0]
        assert risk.severity is Severity.MODERATE

    def test_high_band(self, reading_factory, profile):
        risk = detect_high_temperature(reading_factory(temperature_c=40.0), profile, "customer")[0]
        assert risk.severity is Severity.HIGH

    def test_extreme_band(self, reading_factory, profile):
        risk = detect_high_temperature(reading_factory(temperature_c=46.0), profile, "customer")[0]
        assert risk.severity is Severity.EXTREME


class TestHeatStress:
    """Heat stress uses apparent (feels-like) temperature when available."""

    def test_uses_apparent_temperature(self, reading_factory, profile):
        # Air temp 33C but feels-like 41C -> HIGH heat stress.
        risk = detect_heat_stress(reading_factory(temperature_c=33.0, apparent_temperature_c=41.0), profile, "customer")[0]
        assert risk.severity is Severity.HIGH
        assert risk.affected_metric == "apparent_temperature_c"
        assert "Feels-like" in risk.explanation

    def test_falls_back_to_air_temperature(self, reading_factory, profile):
        risk = detect_heat_stress(reading_factory(temperature_c=47.0, apparent_temperature_c=None), profile, "customer")[0]
        assert risk.severity is Severity.EXTREME
        assert risk.affected_metric == "temperature_c"

    def test_below_threshold_not_detected(self, reading_factory, profile):
        assert detect_heat_stress(reading_factory(apparent_temperature_c=31.0), profile, "customer") == []


class TestStrongWind:
    """Baseline (converted from 10.8/17.2/24.5 m/s): 38.9/62.0/88.2 kph."""

    def test_below_moderate_not_detected(self, reading_factory, profile):
        assert detect_strong_wind(reading_factory(wind_kph=38.0), profile, "customer") == []

    def test_moderate_band(self, reading_factory, profile):
        risk = detect_strong_wind(reading_factory(wind_kph=38.9), profile, "customer")[0]
        assert risk.severity is Severity.MODERATE

    def test_high_band(self, reading_factory, profile):
        risk = detect_strong_wind(reading_factory(wind_kph=62.0), profile, "customer")[0]
        assert risk.severity is Severity.HIGH

    def test_extreme_band(self, reading_factory, profile):
        risk = detect_strong_wind(reading_factory(wind_kph=88.2), profile, "customer")[0]
        assert risk.severity is Severity.EXTREME

    def test_gusts_used_when_stronger(self, reading_factory, profile):
        risk = detect_strong_wind(reading_factory(wind_kph=15.0, wind_gust_kph=65.0), profile, "customer")[0]
        assert risk.severity is Severity.HIGH
        assert risk.affected_metric == "wind_gust_kph"


class TestSevereWeather:
    def test_thunderstorm_detected_high(self, reading_factory, profile):
        risk = detect_severe_weather(reading_factory(weather_code=95), profile, "customer")[0]
        assert risk.category is RiskCategory.SEVERE_WEATHER
        assert risk.severity is Severity.HIGH

    def test_hail_thunderstorm_is_extreme(self, reading_factory, profile):
        risk = detect_severe_weather(reading_factory(weather_code=99), profile, "customer")[0]
        assert risk.severity is Severity.EXTREME

    def test_benign_code_not_detected(self, reading_factory, profile):
        assert detect_severe_weather(reading_factory(weather_code=2), profile, "customer") == []

    def test_missing_code_not_detected(self, reading_factory, profile):
        assert detect_severe_weather(reading_factory(weather_code=None), profile, "customer") == []


class TestFloodPotential:
    """Flood thresholds: 64.5 / 115.6 / 204.6 mm."""

    def test_not_detected_below_moderate(self, reading_factory, profile):
        assert detect_flood_potential(reading_factory(rainfall_mm=64.0), profile, "customer") == []

    def test_moderate_band(self, reading_factory, profile):
        risk = detect_flood_potential(reading_factory(rainfall_mm=64.5), profile, "customer")[0]
        assert risk.category is RiskCategory.FLOOD_POTENTIAL
        assert risk.severity is Severity.MODERATE

    def test_high_band(self, reading_factory, profile):
        risk = detect_flood_potential(reading_factory(rainfall_mm=115.6), profile, "customer")[0]
        assert risk.severity is Severity.HIGH

    def test_explanation_never_claims_observed_flooding(self, reading_factory, profile):
        risk = detect_flood_potential(reading_factory(rainfall_mm=200.0), profile, "customer")[0]
        text = risk.explanation.lower()
        assert "flood potential" in text
        assert "not confirmed" in text or "not observed" in text


class TestPoorTravelConditions:
    def test_not_triggered_by_calm_conditions(self, reading_factory, profile):
        assert detect_poor_travel_conditions(reading_factory(), profile, "traveler") == []

    def test_triggered_by_heavy_rain(self, reading_factory, profile):
        risk = detect_poor_travel_conditions(reading_factory(rainfall_mm=70.0), profile, "traveler")[0]
        assert risk.category is RiskCategory.POOR_TRAVEL_CONDITIONS
        assert "rainfall" in risk.explanation

    def test_triggered_by_storm_code(self, reading_factory, profile):
        risk = detect_poor_travel_conditions(reading_factory(weather_code=95), profile, "traveler")[0]
        assert risk.severity is Severity.HIGH
        assert "thunderstorm" in risk.explanation


class TestActivityDisruption:
    def test_not_triggered_by_calm_conditions(self, reading_factory, profile):
        assert detect_activity_disruption(reading_factory(), profile, "customer") == []

    def test_triggered_by_dangerous_heat(self, reading_factory, profile):
        risk = detect_activity_disruption(reading_factory(temperature_c=35.0, apparent_temperature_c=42.0), profile, "customer")[0]
        assert risk.category is RiskCategory.ACTIVITY_DISRUPTION
        assert "heat" in risk.explanation

    def test_multiple_factors_compound(self, reading_factory, profile):
        risk = detect_activity_disruption(
            reading_factory(rainfall_mm=80.0, wind_kph=45.0, weather_code=95),
            profile,
            "customer",
        )[0]
        assert risk.severity is Severity.HIGH


class TestProfileConfiguration:
    def test_profile_has_spec_baselines(self, profile):
        rain = profile.thresholds.rainfall_mm_per_day
        wind = profile.thresholds.wind_kph
        heat = profile.thresholds.temperature_c
        assert (rain.moderate, rain.high, rain.extreme) == (35.6, 64.5, 115.6)
        assert (wind.moderate, wind.high, wind.extreme) == pytest.approx((38.9, 62.0, 88.2))
        assert (heat.moderate, heat.high, heat.extreme) == (32.0, 40.0, 46.0)

    def test_profile_has_all_roles(self, profile):
        from app.services.risk.models import RiskCategory
        from app.services.risk.roles import KNOWN_ROLES

        for role in KNOWN_ROLES:
            assert role in profile.role_priorities
            # Every taxonomy category must be prioritized for every role.
            assert set(profile.role_priorities[role]) == {c.value for c in RiskCategory}

    def test_profile_has_guidance_for_every_category_and_role(self, profile):
        from app.services.risk.guidance import guidance_for
        from app.services.risk.roles import KNOWN_ROLES

        for category in RiskCategory:
            for role in KNOWN_ROLES:
                text = guidance_for(profile, category, role)
                assert isinstance(text, str) and len(text) > 10

    def test_unknown_profile_name_raises(self):
        from app.services.risk.profile import get_risk_profile

        with pytest.raises(ValueError):
            get_risk_profile("no_such_profile")
