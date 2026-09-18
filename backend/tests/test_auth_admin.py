"""Auth + admin API tests.

Run against an isolated in-memory SQLite database (the app's real database
is Postgres) so these tests never need a running database server.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.services.auth.service import hash_password, seed_accounts, verify_password

# Credentials this suite runs against. The app reads account credentials from
# the environment, and a production deployment sets AUTH_ADMIN_* to a real
# secret — so the fixture below pins them. Tests must neither depend on nor be
# broken by whatever a developer's .env happens to contain.
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"

_PINNED_CREDENTIALS = {
    "AUTH_ADMIN_USERNAME": ADMIN_USERNAME,
    "AUTH_ADMIN_PASSWORD": ADMIN_PASSWORD,
    "AUTH_DEMO_USERNAME": DEMO_USERNAME,
    "AUTH_DEMO_PASSWORD": DEMO_PASSWORD,
    "AUTH_JUDGE_USERNAME": "judge",
    "AUTH_JUDGE_PASSWORD": "judge123",
    "AUTH_JUDGE_ENABLED": True,
}


@pytest.fixture
def auth_client(monkeypatch):
    """ASGI client backed by a fresh in-memory DB with seeded accounts.

    The account credentials are pinned to this module's constants so that both
    seeding and login behave identically whatever the ambient environment sets.
    """
    settings = get_settings()
    for name, value in _PINNED_CREDENTIALS.items():
        monkeypatch.setattr(settings, name, value)

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

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


async def _login(client, username, password, role=None):
    return await client.post("/api/v1/auth/login", json={"username": username, "password": password, "role": role})


class TestPasswordHashing:
    def test_round_trip(self):
        stored = hash_password("s3cret-value")
        assert stored.startswith("pbkdf2_sha256$")
        assert "s3cret-value" not in stored
        assert verify_password("s3cret-value", stored) is True

    def test_rejects_wrong_and_malformed(self):
        stored = hash_password("right")
        assert verify_password("wrong", stored) is False
        assert verify_password("right", "not-a-hash") is False
        assert verify_password("right", "") is False

    def test_salted_hashes_differ(self):
        assert hash_password("same") != hash_password("same")


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_locks_in_the_chosen_role(self, auth_client):
        response = await _login(auth_client, ADMIN_USERNAME, ADMIN_PASSWORD, "disaster_management_officer")
        assert response.status_code == 200
        body = response.json()
        assert body["token"]
        assert body["role"] == "disaster_management_officer"
        assert body["user"]["username"] == ADMIN_USERNAME
        assert body["user"]["is_admin"] is True

    @pytest.mark.asyncio
    async def test_role_defaults_to_account_role_when_omitted(self, auth_client):
        response = await _login(auth_client, "demo", DEMO_PASSWORD)
        assert response.status_code == 200
        assert response.json()["role"] == "customer"

    @pytest.mark.asyncio
    async def test_unknown_role_falls_back_to_default(self, auth_client):
        response = await _login(auth_client, "demo", DEMO_PASSWORD, "astronaut")
        assert response.status_code == 200
        assert response.json()["role"] == "customer"

    @pytest.mark.asyncio
    async def test_judge_account_seeds_and_logs_in_as_citizen(self, auth_client):
        response = await _login(auth_client, "judge", "judge123")
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "customer"
        assert body["user"]["is_admin"] is False
        assert body["user"]["display_name"] == "Judge"

    @pytest.mark.asyncio
    async def test_judge_account_can_take_any_role(self, auth_client):
        response = await _login(auth_client, "judge", "judge123", "farmer")
        assert response.status_code == 200
        assert response.json()["role"] == "farmer"

    @pytest.mark.asyncio
    async def test_judge_seeding_disabled_when_flag_off(self, monkeypatch):
        settings = get_settings()
        for name, value in _PINNED_CREDENTIALS.items():
            monkeypatch.setattr(settings, name, value)
        monkeypatch.setattr(settings, "AUTH_JUDGE_ENABLED", False)
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(bind=engine)
        with TestingSession() as db:
            created = seed_accounts(db)
        assert "judge" not in created
        assert "demo" in created

        def _override_get_db():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/login", json={"username": "judge", "password": "judge123", "role": None}
                )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)
            engine.dispose()

    @pytest.mark.asyncio
    async def test_wrong_password_and_unknown_user_are_indistinguishable(self, auth_client):
        wrong = await _login(auth_client, "demo", "nope")
        unknown = await _login(auth_client, "ghost", "nope")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"]


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_session_lookup_requires_a_token(self, auth_client):
        assert (await auth_client.get("/api/v1/auth/session")).status_code == 401

    @pytest.mark.asyncio
    async def test_session_returns_the_locked_role(self, auth_client):
        token = (await _login(auth_client, "demo", DEMO_PASSWORD, "traveler")).json()["token"]
        response = await auth_client.get("/api/v1/auth/session", headers={"X-Session-Token": token})
        assert response.status_code == 200
        assert response.json()["role"] == "traveler"

    @pytest.mark.asyncio
    async def test_logout_revokes_the_token(self, auth_client):
        token = (await _login(auth_client, "demo", DEMO_PASSWORD)).json()["token"]
        headers = {"X-Session-Token": token}
        assert (await auth_client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
        assert (await auth_client.get("/api/v1/auth/session", headers=headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_is_rejected(self, auth_client):
        response = await auth_client.get("/api/v1/auth/session", headers={"X-Session-Token": "nonsense"})
        assert response.status_code == 401


class TestRoleLockOnDataEndpoints:
    @pytest.mark.asyncio
    async def test_session_role_overrides_the_requested_role(self, auth_client, stub_calm_provider):
        token = (await _login(auth_client, "demo", DEMO_PASSWORD, "farmer")).json()["token"]
        response = await auth_client.get(
            "/api/v1/risk?latitude=19.076&longitude=72.8777&role=customer",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        # The client asked for "customer"; the session's locked role wins.
        assert response.json()["role"] == "farmer"

    @pytest.mark.asyncio
    async def test_without_a_session_the_requested_role_is_honoured(self, auth_client, stub_calm_provider):
        response = await auth_client.get("/api/v1/risk?latitude=19.076&longitude=72.8777&role=traveler")
        assert response.status_code == 200
        assert response.json()["role"] == "traveler"

    @pytest.mark.asyncio
    async def test_safety_endpoint_also_locks_the_role(self, auth_client, stub_calm_provider):
        token = (await _login(auth_client, "demo", DEMO_PASSWORD, "farmer")).json()["token"]
        response = await auth_client.get(
            "/api/v1/safety?latitude=19.076&longitude=72.8777&role=customer",
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "farmer"


class TestAdminPanel:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, auth_client):
        assert (await auth_client.get("/api/v1/admin/overview")).status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_is_forbidden(self, auth_client):
        token = (await _login(auth_client, "demo", DEMO_PASSWORD)).json()["token"]
        response = await auth_client.get("/api/v1/admin/overview", headers={"X-Session-Token": token})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_overview_reports_the_model_stack(self, auth_client):
        token = (await _login(auth_client, ADMIN_USERNAME, ADMIN_PASSWORD)).json()["token"]
        response = await auth_client.get("/api/v1/admin/overview", headers={"X-Session-Token": token})
        assert response.status_code == 200
        body = response.json()

        assert body["model"]["provider_mode"]
        assert isinstance(body["model"]["tiers"], list) and body["model"]["tiers"]
        assert "metrics" in body["model"]
        assert body["model"]["metrics"]["requests"] >= 0
        # Deterministic layer the model is grounded in.
        assert body["deterministic_layer"]["risk_engine"]["profile"]
        assert body["deterministic_layer"]["data_sources"]["weather_provider"]
        assert body["database"]["reachable"] is True
        assert body["database"]["accounts"] >= 2

    @pytest.mark.asyncio
    async def test_sessions_listing_shows_the_locked_role(self, auth_client):
        token = (await _login(auth_client, ADMIN_USERNAME, ADMIN_PASSWORD, "farmer")).json()["token"]
        response = await auth_client.get("/api/v1/admin/sessions", headers={"X-Session-Token": token})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] >= 1
        first = body["sessions"][0]
        assert first["username"] == ADMIN_USERNAME
        assert first["session_role"] == "farmer"
        assert first["account_role"] == "disaster_management_officer"
        assert first["role_locked"] is True
