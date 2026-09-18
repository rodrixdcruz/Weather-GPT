"""Judge-only scenario simulation: the overlay provider and the API gate."""
import httpx
import pytest

from app.core.config import get_settings
from app.services.weather.base import WeatherReading
from app.services.weather.scenario_overlay import bend_reading, bend_forecast


def _live_reading(**overrides) -> WeatherReading:
    base = dict(
        location_label="19.076, 72.878",
        latitude=19.076,
        longitude=72.8777,
        observed_at="2026-09-17T21:00",
        temperature_c=27.0,
        condition="Light drizzle",
        rainfall_mm=0.2,
        precip_probability_pct=20.0,
        humidity_pct=70.0,
        wind_kph=9.0,
        source="open-meteo",
        is_verified=True,
        apparent_temperature_c=29.0,
        wind_gust_kph=14.0,
    )
    base.update(overrides)
    return WeatherReading(**base)


class TestBendReading:
    def test_heavy_rainfall_raises_rain_but_keeps_real_baseline(self):
        bent = bend_reading(_live_reading(), "heavy_rainfall")
        assert bent.rainfall_mm == 68.0  # lifted to the target
        assert bent.precip_probability_pct == 92.0
        # A genuinely drier real reading is bent harder; a wetter one is kept.
        wetter = bend_reading(_live_reading(rainfall_mm=80.0), "heavy_rainfall")
        assert wetter.rainfall_mm == 80.0

    def test_heatwave_sets_temperature_drops_humidity(self):
        bent = bend_reading(_live_reading(), "heatwave")
        assert bent.temperature_c == 43.0
        assert bent.apparent_temperature_c == 47.5
        assert bent.humidity_pct == 28.0
        assert bent.rainfall_mm == 0.0

    def test_thunderstorm_bends_wind_and_gusts(self):
        bent = bend_reading(_live_reading(), "thunderstorm")
        assert bent.wind_kph == 38.0
        assert bent.wind_gust_kph == 55.0

    def test_flood_risk_extreme_rain(self):
        bent = bend_reading(_live_reading(), "flood_risk")
        assert bent.rainfall_mm == 110.0
        assert bent.precip_probability_pct == 97.0

    def test_smog_bends_existing_aqi_with_overlay_provenance(self):
        from app.services.weather.air_quality import AirQuality

        reading = _live_reading(
            air_quality=AirQuality(
                observed_at="2026-09-17T21:00",
                us_aqi=42.0,
                pm2_5=19.0,
                pm10=31.0,
                band="Good",
                source="open-meteo",
                is_verified=True,
            )
        )
        bent = bend_reading(reading, "smog")
        assert bent.air_quality.us_aqi == 168.0
        assert bent.air_quality.source == "scenario_overlay"
        assert bent.air_quality.is_verified is False

    def test_smog_without_aqi_enrichment_builds_labeled_fixture(self):
        bent = bend_reading(_live_reading(air_quality=None), "smog")
        assert bent.air_quality is not None
        assert bent.air_quality.us_aqi == 168.0
        assert bent.air_quality.is_verified is False
        assert bent.air_quality.source == "scenario_overlay"

    def test_honesty_is_structural(self):
        """Every bend keeps the real coordinates/time and flips provenance."""
        for name in ("heavy_rainfall", "heatwave", "thunderstorm", "flood_risk", "smog"):
            bent = bend_reading(_live_reading(), name)
            assert bent.is_verified is False, name
            assert bent.source == f"scenario_overlay:{name}", name
            assert bent.latitude == 19.076
            assert bent.observed_at == "2026-09-17T21:00"

    def test_unknown_scenario_is_a_no_op(self):
        assert bend_reading(_live_reading(), "zombie_apocalypse").is_verified is True


class TestBendForecast:
    def test_forecast_follows_the_scenario(self):
        from app.services.weather.base import ForecastDay

        days = [
            ForecastDay(date=f"day{i}", rainfall_mm=1.0, temperature_c=30.0, wind_max_kph=10.0)
            for i in range(3)
        ]
        bent = bend_forecast(days, "heavy_rainfall")
        assert all(d.rainfall_mm == 68.0 for d in bent)
        heat = bend_forecast(days, "heatwave")
        assert all(d.temperature_c == 43.0 for d in heat)


class TestResolveDemoScenario:
    def _session_for(self, username):
        class _Acc:
            pass

        class _Sess:
            pass

        acc = _Acc()
        acc.username = username
        sess = _Sess()
        sess.account = acc
        return sess

    def test_normal_always_allowed(self):
        from app.services.weather.factory import resolve_demo_scenario

        assert resolve_demo_scenario("normal", self._session_for("demo")) == "normal"
        assert resolve_demo_scenario(None, None) == "normal"

    def test_non_judge_silently_downgraded_to_live(self):
        from app.services.weather.factory import resolve_demo_scenario

        assert resolve_demo_scenario("flood_risk", self._session_for("demo")) == "normal"
        assert resolve_demo_scenario("flood_risk", None) == "normal"

    def test_judge_gets_the_scenario(self):
        from app.services.weather.factory import resolve_demo_scenario

        settings = get_settings()
        assert settings.AUTH_JUDGE_ENABLED
        assert resolve_demo_scenario("smog", self._session_for(settings.AUTH_JUDGE_USERNAME)) == "smog"

    def test_unknown_scenario_rejected_even_for_judge(self):
        from app.services.weather.factory import resolve_demo_scenario

        with pytest.raises(Exception) as excinfo:
            resolve_demo_scenario("meteor", self._session_for("judge"))
        assert getattr(excinfo.value, "status_code", None) == 403 or "403" in str(excinfo.value)


class TestScenarioGateEndToEnd:
    """The API must serve bent weather to a judge session and live data to everyone else."""

    @pytest.fixture
    def auth_client(self, monkeypatch):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db.session import Base, get_db
        from app.main import app
        from app.services.auth.service import seed_accounts

        settings = get_settings()
        monkeypatch.setattr(settings, "AUTH_ADMIN_USERNAME", "admin")
        monkeypatch.setattr(settings, "AUTH_ADMIN_PASSWORD", "admin123")
        monkeypatch.setattr(settings, "AUTH_DEMO_USERNAME", "demo")
        monkeypatch.setattr(settings, "AUTH_DEMO_PASSWORD", "demo123")
        monkeypatch.setattr(settings, "AUTH_JUDGE_USERNAME", "judge")
        monkeypatch.setattr(settings, "AUTH_JUDGE_PASSWORD", "judge123")
        monkeypatch.setattr(settings, "AUTH_JUDGE_ENABLED", True)
        # Force the mock provider so the test is hermetic (no live weather HTTP).
        monkeypatch.setattr(settings, "WEATHER_PROVIDER", "mock")

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(bind=engine)
        with TestingSession() as db:
            seed_accounts(db)

        def _override():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override
        try:
            yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

    async def _login_token(self, client, username, password):
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password, "role": None}
        )
        assert response.status_code == 200
        return response.json()["token"]

    @pytest.mark.asyncio
    async def test_judge_session_gets_scenario_weather(self, auth_client):
        token = await self._login_token(auth_client, "judge", "judge123")
        response = await auth_client.get(
            "/api/v1/weather/current?latitude=19.076&longitude=72.8777&scenario=flood_risk",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["weather"]["rainfall_mm"] == 110.0
        assert body["weather"]["is_verified"] is False
        assert body["weather"]["source"] == "mock_fixture"  # mock fixtures keep their provenance

    @pytest.mark.asyncio
    async def test_judge_scenario_headline_is_most_severe_risk(self, auth_client):
        """The legacy embedded risk must headline the WORST risk, not the first.

        Regression: /weather/current used assessment.risks[0], which is sorted
        by role priority — so air_quality (moderate) won the headline while
        rainfall sat at HIGH under the flood scenario.
        """
        token = await self._login_token(auth_client, "judge", "judge123")
        response = await auth_client.get(
            "/api/v1/weather/current?latitude=19.076&longitude=72.8777&scenario=flood_risk",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["risk"]["level"] in ("high", "extreme")
        assert body["risk"]["hazard_type"] == "rainfall"

    @pytest.mark.asyncio
    async def test_demo_session_asking_for_scenario_gets_live(self, auth_client):
        token = await self._login_token(auth_client, "demo", "demo123")
        response = await auth_client.get(
            "/api/v1/weather/current?latitude=19.076&longitude=72.8777&scenario=flood_risk",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["weather"]["rainfall_mm"] == 2.0  # the mock's normal fixture
        assert body["risk"]["level"] == "low"

    @pytest.mark.asyncio
    async def test_risk_endpoint_follows_scenario_for_judge(self, auth_client):
        token = await self._login_token(auth_client, "judge", "judge123")
        response = await auth_client.get(
            "/api/v1/risk?latitude=19.076&longitude=72.8777&scenario=flood_risk",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["overall_severity"] in ("high", "extreme")
        assert any(r["category"] == "rainfall" for r in body["risks"])
