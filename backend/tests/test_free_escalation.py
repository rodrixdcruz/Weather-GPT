"""
Tests for the FREE escalation tier that replaced Solar Pro 4.

Covers the preset table, provider resolution (explicit / auto-by-key), the
keyless path (no Authorization header at all), and the free-tier-specific
failure modes (429 rate limit, missing key). All HTTP is mocked, so no real
provider account or network access is needed.
"""
import json

import httpx
import pytest

from app.services.ai.base import AIProviderError, ChatTurn, WeatherContext
from app.services.ai.cloud_provider import CloudChatProvider
from app.services.ai.presets import (
    KEYED_DEFAULT,
    KEYLESS_FALLBACK,
    PRESETS,
    choose_preset_name,
    get_preset,
    preset_names,
)
from app.services.ai.solar_provider import SolarProvider


def _context(**overrides) -> WeatherContext:
    base = dict(
        location_label="19.076, 72.878",
        latitude=19.076,
        longitude=72.8777,
        observed_at="2026-09-09T06:00",
        temperature_c=29.0,
        condition="Partly cloudy",
        rainfall_mm=2.0,
        precip_probability_pct=10.0,
        humidity_pct=55.0,
        wind_kph=12.0,
        risk_level="low",
        risk_score=12.0,
        hazard_type=None,
        is_verified=False,
        source="test",
    )
    base.update(overrides)
    return WeatherContext(**base)


def _ok(content="Free tier reply"):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


class TestPresetTable:
    def test_every_preset_is_complete(self):
        for name, preset in PRESETS.items():
            assert preset.name == name
            assert preset.base_url.startswith("https://"), name
            assert preset.model, name
            assert preset.limits, name
            # A keyed preset must tell the operator where to get the key.
            if preset.requires_key:
                assert preset.signup_url, f"{name} requires a key but has no signup URL"

    def test_keyless_preset_exists(self):
        """The keyless tier is what makes escalation work with zero setup."""
        keyless = [p for p in PRESETS.values() if not p.requires_key]
        assert keyless, "at least one preset must work without an API key"
        assert all(p.signup_url is None for p in keyless if not p.requires_key)

    def test_solar_is_kept_but_is_not_the_default(self):
        assert "solar" in PRESETS  # back-compat for existing paid keys
        assert KEYED_DEFAULT == "groq"
        assert KEYLESS_FALLBACK == "ovhcloud"

    def test_unknown_preset_lists_valid_options(self):
        with pytest.raises(ValueError) as excinfo:
            get_preset("definitely-not-a-provider")
        message = str(excinfo.value)
        assert "groq" in message and "ovhcloud" in message
        assert preset_names() == sorted(PRESETS)

    def test_auto_resolution_prefers_a_real_key(self):
        assert choose_preset_name(provider=None, has_api_key=True) == KEYED_DEFAULT
        assert choose_preset_name(provider="auto", has_api_key=True) == KEYED_DEFAULT
        assert choose_preset_name(provider="auto", has_api_key=False) == KEYLESS_FALLBACK
        assert choose_preset_name(provider="", has_api_key=False) == KEYLESS_FALLBACK

    def test_explicit_choice_always_wins(self):
        assert choose_preset_name(provider="gemini", has_api_key=False) == "gemini"
        assert choose_preset_name(provider="OVHcloud", has_api_key=True) == "ovhcloud"


class TestCloudChatProvider:
    async def test_keyless_provider_needs_no_authorization_header(self):
        """The whole point of the keyless tier: it works with no key at all."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            captured["url"] = str(request.url)
            return _ok()

        provider = CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None)
        provider._transport = httpx.MockTransport(handler)

        assert await provider.is_available() is True
        reply = await provider.generate_reply("Will it rain today?", [], _context())

        assert reply.text == "Free tier reply"
        assert reply.provider == "ovhcloud"
        assert "authorization" not in captured
        assert captured["url"] == f"{get_preset('ovhcloud').base_url}/chat/completions"

    async def test_keyed_provider_without_key_is_unavailable_and_actionable(self):
        provider = CloudChatProvider(preset=get_preset("groq"), api_key=None)

        assert await provider.is_available() is False
        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("rain?", [], _context())

        assert excinfo.value.kind == "unavailable"
        # The message must tell the operator what to actually do.
        assert "ESCALATION_API_KEY" in excinfo.value.detail
        assert "ovhcloud" in excinfo.value.detail

    async def test_keyed_provider_sends_bearer_token(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            captured["model"] = json.loads(request.content)["model"]
            return _ok()

        provider = CloudChatProvider(preset=get_preset("groq"), api_key="free-key-abc")
        provider._transport = httpx.MockTransport(handler)

        assert await provider.is_available() is True
        await provider.generate_reply("rain?", [], _context())

        assert captured["auth"] == "Bearer free-key-abc"
        assert captured["model"] == get_preset("groq").model

    async def test_base_url_and_model_are_overridable(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["model"] = json.loads(request.content)["model"]
            return _ok()

        provider = CloudChatProvider(
            preset=get_preset("groq"),
            api_key="k",
            base_url="https://self-hosted.example/v1/",
            model="my-own-model",
        )
        provider._transport = httpx.MockTransport(handler)
        await provider.generate_reply("rain?", [], _context())

        assert captured["url"] == "https://self-hosted.example/v1/chat/completions"
        assert captured["model"] == "my-own-model"

    async def test_rate_limit_gets_its_own_kind(self):
        """A 429 is the expected failure on a free tier — it must be named."""
        provider = CloudChatProvider(preset=get_preset("groq"), api_key="k")
        provider._transport = httpx.MockTransport(lambda req: httpx.Response(429, json={"error": "slow down"}))

        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("rain?", [], _context())

        assert excinfo.value.kind == "rate_limited"
        assert get_preset("groq").limits in excinfo.value.detail

    async def test_grounding_prompt_and_role_are_carried(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["prompt"] = json.loads(request.content)["messages"][-1]["content"]
            return _ok()

        provider = CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None)
        provider._transport = httpx.MockTransport(handler)
        await provider.generate_reply(
            "rain?",
            [ChatTurn(role="user", content="hi")],
            _context(),
            retrieved=[{"title": "Heavy Rain Safety Basics", "content": "Avoid waterlogged roads."}],
            role="farmer",
        )

        assert "rainfall_mm" in captured["prompt"]
        assert "Heavy Rain Safety Basics" in captured["prompt"]
        assert "farmer" in captured["prompt"]

    async def test_credentials_are_never_exposed(self):
        provider = CloudChatProvider(preset=get_preset("groq"), api_key="super-secret")
        # The panel may know a key exists; it must never be able to read it.
        assert provider.has_credentials is True
        assert "super-secret" not in json.dumps(
            [provider.provider_name, provider.model, provider.base_url, provider.preset.name]
        )
        assert not hasattr(provider, "api_key")


class TestBroadKnowledgeRouting:
    """Escalation is free now, so 'explain the phenomenon' questions must
    actually reach the cloud tier instead of getting a small local model's
    "my context doesn't include that" non-answer."""

    def setup_method(self):
        from app.services.ai.scope_guard import ScopeGuard, ScopeVerdict

        self.guard = ScopeGuard()
        self.BROAD = ScopeVerdict.BROAD_KNOWLEDGE
        self.IN_SCOPE = ScopeVerdict.IN_SCOPE

    @pytest.mark.parametrize(
        "question",
        [
            # The exact phrasing that used to slip through and stay local.
            "Explain what El Nino is and how it changes rainfall patterns",
            "Explain El Nino and its history on worldwide rainfall patterns",
            "Tell me about El Nino",
            "What is climate change?",
            "what causes lightning?",
            "How does a cyclone form?",
            "Describe the monsoon season",
            "What is a rain shadow?",
            "Difference between a hurricane and a typhoon",
            "Explain the urban heat island effect",
            "What is the jet stream?",
            "Tell me about drought",
        ],
    )
    def test_knowledge_questions_escalate(self, question):
        assert self.guard.classify(question) is self.BROAD, question

    @pytest.mark.parametrize(
        "question",
        [
            # Local conditions must NOT escalate: the local model has the real
            # numbers, and the cloud tier would only be slower.
            "What is the current weather?",
            "Will it rain today?",
            "Is it safe to go outside?",
            "What is the humidity right now?",
            "How hot will it get?",
            "Will there be lightning today?",
            "Is there a thunderstorm risk this evening?",
            "What is the rainfall so far?",
            "Should I harvest before the rain arrives?",
            "Can I spray my fields this afternoon?",
            "What are the current weather risks?",
        ],
    )
    def test_local_questions_stay_local(self, question):
        assert self.guard.classify(question) is self.IN_SCOPE, question

    def test_nonsense_is_still_refused(self):
        from app.services.ai.scope_guard import ScopeVerdict

        assert self.guard.classify("svgsvgsvg") is ScopeVerdict.OUT_OF_SCOPE
        assert self.guard.classify("asdf jkl") is ScopeVerdict.OUT_OF_SCOPE


class TestEnvDrivenResolution:
    def _provider_with_env(self, monkeypatch, **env):
        from app.core.config import get_settings

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        try:
            return CloudChatProvider()
        finally:
            for key in env:
                monkeypatch.delenv(key, raising=False)
            get_settings.cache_clear()

    def test_auto_with_key_selects_groq(self, monkeypatch):
        provider = self._provider_with_env(monkeypatch, ESCALATION_PROVIDER="auto", ESCALATION_API_KEY="free-key")
        assert provider.provider_name == "groq"
        assert provider.model == get_preset("groq").model

    def test_auto_without_key_falls_back_to_keyless(self, monkeypatch):
        provider = self._provider_with_env(monkeypatch, ESCALATION_PROVIDER="auto", ESCALATION_API_KEY="")
        assert provider.provider_name == "ovhcloud"
        assert provider.has_credentials is False

    def test_explicit_provider_and_overrides(self, monkeypatch):
        provider = self._provider_with_env(
            monkeypatch,
            ESCALATION_PROVIDER="gemini",
            ESCALATION_API_KEY="g-key",
            ESCALATION_MODEL="custom-gemini-id",
            ESCALATION_BASE_URL="https://example.test/v1",
        )
        assert provider.provider_name == "gemini"
        assert provider.model == "custom-gemini-id"
        assert provider.base_url == "https://example.test/v1"


class TestSolarBackCompat:
    async def test_solar_provider_still_works_and_reports_itself(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/chat/completions")
            return _ok("solar reply")

        provider = SolarProvider(api_key="legacy-key", model="solar-pro4")
        provider._transport = httpx.MockTransport(handler)

        assert await provider.is_available() is True
        reply = await provider.generate_reply("rain?", [], _context())
        assert reply.text == "solar reply"
        assert reply.provider == "solar"

    def test_solar_uses_its_own_env_vars_not_escalation(self, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("SOLAR_API_BASE_URL", "https://solar.example/v1")
        monkeypatch.setenv("SOLAR_MODEL", "solar-pro4")
        monkeypatch.setenv("ESCALATION_BASE_URL", "https://wrong.example/v1")
        get_settings.cache_clear()
        try:
            provider = SolarProvider(api_key="k")
            assert provider.base_url == "https://solar.example/v1"
            assert provider.model == "solar-pro4"
            assert provider.provider_name == "solar"
        finally:
            monkeypatch.delenv("SOLAR_API_BASE_URL", raising=False)
            monkeypatch.delenv("ESCALATION_BASE_URL", raising=False)
            get_settings.cache_clear()


class TestHybridUsesFreeTier:
    async def test_escalation_name_is_reported_for_logs(self, monkeypatch):
        from app.services.ai.hybrid_provider import HybridAIProvider
        from app.services.ai.scope_guard import ScopeGuard

        hybrid = HybridAIProvider(
            primary=CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None),
            escalation=CloudChatProvider(preset=get_preset("groq"), api_key="k"),
            scope_guard=ScopeGuard(),
        )
        assert hybrid.escalation_name == "groq"

    async def test_broad_knowledge_question_is_served_by_the_free_tier(self):
        """The user-facing point: 'extra knowledge' questions still get a real
        model answer, now from a free provider rather than a paid one."""
        from app.services.ai.hybrid_provider import HybridAIProvider
        from app.services.ai.scope_guard import ScopeGuard

        def handler(request: httpx.Request) -> httpx.Response:
            return _ok("El Nino is a climate pattern that shifts rainfall.")

        escalation = CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None)
        escalation._transport = httpx.MockTransport(handler)

        class _NeverCalledLocal(CloudChatProvider):
            async def generate_reply(self, *args, **kwargs):  # pragma: no cover - must not run
                raise AssertionError("broad-knowledge questions should skip the local tier")

        hybrid = HybridAIProvider(
            primary=_NeverCalledLocal(preset=get_preset("ovhcloud"), api_key=None),
            escalation=escalation,
            scope_guard=ScopeGuard(),
        )

        reply = await hybrid.generate_reply("Explain El Nino and its effect on rainfall", [], _context())
        assert reply.provider == "ovhcloud"
        assert "El Nino" in reply.text
