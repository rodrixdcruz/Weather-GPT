"""Tests for the hybrid AI routing (Ollama first → Solar Pro 4 escalation
→ data fallback) and the scope guard.

All HTTP is mocked (httpx.MockTransport / stub providers); no real Ollama
server or Solar API key is needed. The chat router's data-based fallback
semantics must remain intact: `fallback_used=true` ONLY when both tiers
fail.
"""
import json

import httpx
import pytest

from app.services.ai.base import AIProvider, AIProviderError, AIReply, ChatTurn, WeatherContext
from app.services.ai.factory import get_ai_provider, reset_ai_provider_cache
from app.services.ai.hybrid_provider import HybridAIProvider
from app.services.ai.scope_guard import ScopeGuard, ScopeVerdict, _is_gibberish
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


class _StubProvider(AIProvider):
    """Configurable provider double for routing tests."""

    def __init__(self, *, reply=None, error=None, name="stub"):
        self._reply = reply
        self._error = error
        self.name = name
        self.calls = 0

    async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._reply or AIReply(text=f"{self.name} answer", language=language, provider=self.name)


class TestHybridRouting:
    async def test_ollama_success_solar_not_called(self):
        primary = _StubProvider(name="ollama")
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply("Will it rain today?", [], _context())

        assert reply.text == "ollama answer"
        assert reply.provider == "ollama"
        assert primary.calls == 1
        assert escalation.calls == 0  # SIH cost rule: local first, no API spend

    async def test_ollama_failure_escalates_to_solar(self):
        primary = _StubProvider(error=AIProviderError("unavailable", "down"))
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply("Will it rain today?", [], _context())

        assert reply.text == "solar answer"
        assert reply.provider == "solar"
        assert primary.calls == 1
        assert escalation.calls == 1

    async def test_ollama_timeout_escalates_to_solar(self):
        # The Ollama provider maps timeouts to kind="unavailable"; a stub
        # with the same typed error exercises the identical code path.
        primary = _StubProvider(error=AIProviderError("unavailable", "Local AI did not respond in time."))
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply("Will it rain today?", [], _context())

        assert reply.provider == "solar"

    async def test_both_fail_raises_typed_error_for_data_fallback(self):
        primary = _StubProvider(error=AIProviderError("unavailable", "down"))
        escalation = _StubProvider(error=AIProviderError("unavailable", "solar down"))
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        with pytest.raises(AIProviderError):
            await hybrid.generate_reply("Will it rain today?", [], _context())

    async def test_broad_knowledge_skips_ollama_goes_to_solar(self):
        primary = _StubProvider(name="ollama")
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply(
            "Explain El Nino and its history on worldwide rainfall patterns", [], _context()
        )

        assert reply.provider == "solar"
        assert primary.calls == 0  # broad-knowledge flag skips tier 1

    async def test_out_of_scope_refuses_without_any_ai_call(self):
        primary = _StubProvider(name="ollama")
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply("svgsvgsvg", [], _context())

        assert reply.provider == "scope_guard"
        assert "weather" in reply.text.lower()
        assert primary.calls == 0
        assert escalation.calls == 0

    async def test_unexpected_primary_error_still_escalates(self):
        class _Broken(_StubProvider):
            async def generate_reply(self, *args, **kwargs):
                self.calls += 1
                raise RuntimeError("bug in provider code")

        primary = _Broken(name="ollama")
        escalation = _StubProvider(name="solar")
        hybrid = HybridAIProvider(primary=primary, escalation=escalation, scope_guard=ScopeGuard())

        reply = await hybrid.generate_reply("Will it rain today?", [], _context())
        assert reply.provider == "solar"

    async def test_solar_key_missing_falls_through_to_data_fallback_error(self):
        """Spec scenario 6: no Solar key + Ollama down = graceful data fallback
        (router sees the typed error and answers from real data)."""
        solar = SolarProvider(api_key=None)
        solar._api_key = None  # force, even if the test env has a key
        hybrid = HybridAIProvider(
            primary=_StubProvider(error=AIProviderError("unavailable", "ollama down")),
            escalation=solar,
            scope_guard=ScopeGuard(),
        )
        with pytest.raises(AIProviderError) as excinfo:
            await hybrid.generate_reply("Will it rain today?", [], _context())
        assert excinfo.value.kind == "unavailable"

    async def test_unexpected_solar_error_normalized_to_typed_error(self):
        class _Broken(AIProvider):
            async def generate_reply(self, *args, **kwargs):
                raise RuntimeError("bug")

        hybrid = HybridAIProvider(
            primary=_StubProvider(error=AIProviderError("unavailable", "down")),
            escalation=_Broken(),
            scope_guard=ScopeGuard(),
        )
        with pytest.raises(AIProviderError):
            await hybrid.generate_reply("rain?", [], _context())


class TestScopeGuard:
    def setup_method(self):
        self.guard = ScopeGuard()

    def test_nonsense_is_out_of_scope(self):
        assert self.guard.classify("svgsvgsvg") is ScopeVerdict.OUT_OF_SCOPE
        assert self.guard.classify("asdf jkl") is ScopeVerdict.OUT_OF_SCOPE
        assert self.guard.classify("123123 !!!") is ScopeVerdict.OUT_OF_SCOPE

    def test_normal_weather_questions_in_scope(self):
        for q in [
            "What is the current weather?",
            "Will it rain today?",
            "Is it safe to go outside?",
            "How should a farmer plan work today?",
            "What are the current weather risks?",
            "Should I travel today?",
            "Should I harvest before the rain arrives?",
        ]:
            assert self.guard.classify(q) is ScopeVerdict.IN_SCOPE, q

    def test_no_weather_word_still_in_scope(self):
        # The spec's rule: legitimate natural language must not be rejected
        # just because it lacks the word "weather".
        assert self.guard.classify("Can I spray my fields this afternoon?") is ScopeVerdict.IN_SCOPE
        assert self.guard.classify("Are the roads safe for driving tomorrow?") is ScopeVerdict.IN_SCOPE

    def test_greetings_pass_through(self):
        assert self.guard.classify("hi") is ScopeVerdict.IN_SCOPE
        assert self.guard.classify("नमस्ते") is ScopeVerdict.IN_SCOPE

    def test_hindi_and_marathi_questions_in_scope(self):
        assert self.guard.classify("क्या आज बारिश होगी?") is ScopeVerdict.IN_SCOPE
        assert self.guard.classify("आज पाऊस पडेल का?") is ScopeVerdict.IN_SCOPE

    def test_broad_knowledge_detected(self):
        assert self.guard.classify("What is climate change?") is ScopeVerdict.BROAD_KNOWLEDGE
        assert self.guard.classify("Tell me about El Nino") is ScopeVerdict.BROAD_KNOWLEDGE
        assert self.guard.classify("Show me historical weather data for Mumbai") is ScopeVerdict.BROAD_KNOWLEDGE

    def test_gibberish_heuristics(self):
        assert _is_gibberish("svgsvgsvg")
        assert _is_gibberish("xyzzy")
        assert not _is_gibberish("rain")
        assert not _is_gibberish("Will it rain today?")

    def test_empty_is_out_of_scope(self):
        assert self.guard.classify("") is ScopeVerdict.OUT_OF_SCOPE
        assert self.guard.classify("   ") is ScopeVerdict.OUT_OF_SCOPE


class TestSolarProvider:
    def _provider(self, handler, api_key="test-key-123"):
        provider = SolarProvider(api_key=api_key, model="solar-pro4")
        provider._transport = httpx.MockTransport(handler)
        return provider

    async def test_successful_reply(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "solar-pro4"
            assert request.url.path.endswith("/chat/completions")
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Solar reply"}}]})

        reply = await self._provider(handler).generate_reply("rain?", [], _context())
        assert reply.text == "Solar reply"
        assert reply.provider == "solar"

    async def test_missing_key_raises_typed_error(self):
        provider = SolarProvider(api_key=None)
        provider._api_key = None  # force even if env has a key
        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("rain?", [], _context())
        assert excinfo.value.kind == "unavailable"

    async def test_timeout_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout")

        with pytest.raises(AIProviderError) as excinfo:
            await self._provider(handler).generate_reply("rain?", [], _context())
        assert excinfo.value.kind == "unavailable"

    async def test_http_401_maps_to_unavailable(self):
        with pytest.raises(AIProviderError):
            await self._provider(lambda req: httpx.Response(401, json={"detail": "bad key"})).generate_reply("rain?", [], _context())

    async def test_http_404_maps_to_model_missing(self):
        with pytest.raises(AIProviderError) as excinfo:
            await self._provider(lambda req: httpx.Response(404, json={"detail": "no model"})).generate_reply("rain?", [], _context())
        assert excinfo.value.kind == "model_missing"

    async def test_prompt_carries_grounding_and_role(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["prompt"] = json.loads(request.content)["messages"][-1]["content"]
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        await self._provider(handler).generate_reply(
            "rain?",
            [ChatTurn(role="user", content="hi")],
            _context(),
            retrieved=[{"title": "Heavy Rain Safety Basics", "content": "Avoid waterlogged roads."}],
            role="farmer",
        )
        assert "rainfall_mm" in captured["prompt"]
        assert "Heavy Rain Safety Basics" in captured["prompt"]
        assert "farmer" in captured["prompt"]


class TestFactoryHybrid:
    def test_factory_selects_hybrid(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "hybrid")
        from app.core.config import get_settings

        get_settings.cache_clear()
        reset_ai_provider_cache()
        try:
            assert type(get_ai_provider()).__name__ == "HybridAIProvider"
        finally:
            get_settings.cache_clear()
            monkeypatch.delenv("AI_PROVIDER", raising=False)
            get_settings.cache_clear()
            reset_ai_provider_cache()


class TestChatEndpointHybrid:
    async def test_chat_ollama_served_no_fallback(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        class _FakeHybrid(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="Local AI says: light rain only.", language=language, provider="ollama")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _FakeHybrid())
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "Will it rain today?", "session_id": "hyb-1", "latitude": 19.076, "longitude": 72.8777},
        )
        body = response.json()
        assert body["fallback_used"] is False
        assert body["provider"] == "ollama"
        assert body["reply"] == "Local AI says: light rain only."

    async def test_chat_solar_escalation_no_fallback(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        class _FakeHybrid(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="Solar says: 2 mm expected.", language=language, provider="solar")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _FakeHybrid())
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "Will it rain today?", "session_id": "hyb-2", "latitude": 19.076, "longitude": 72.8777},
        )
        body = response.json()
        assert body["fallback_used"] is False, "Solar success must NOT show the unavailable banner"
        assert body["provider"] == "solar"

    async def test_chat_both_fail_uses_data_fallback(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        class _FakeHybrid(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                raise AIProviderError("unavailable", "both tiers down")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _FakeHybrid())
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "Will it rain today?", "session_id": "hyb-3", "latitude": 19.076, "longitude": 72.8777},
        )
        body = response.json()
        assert body["fallback_used"] is True
        assert body["provider"] == "fallback"
        assert "mm" in body["reply"]  # still grounded in real data

    async def test_chat_nonsense_gets_scope_reply_without_ai(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        called = {"n": 0}

        class _Counting(AIProvider):
            async def generate_reply(self, message, history, context, **kwargs):
                called["n"] += 1
                return AIReply(text="should not be reached", provider="ollama")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _Counting())
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "svgsvgsvg", "session_id": "hyb-4", "latitude": 19.076, "longitude": 72.8777},
        )
        body = response.json()
        assert called["n"] == 0, "scope reply must not consume an AI call"
        assert body["provider"] == "scope_guard"
        assert body["fallback_used"] is False
        assert "weather" in body["reply"].lower()

    async def test_chat_response_never_contains_api_key(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        class _FakeHybrid(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="answer", provider="solar")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _FakeHybrid())
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "rain?", "session_id": "hyb-5", "latitude": 19.076, "longitude": 72.8777},
        )
        assert response.status_code == 200
        assert "sk-test-key" not in response.text
        assert "SOLAR_API_KEY" not in response.text
        assert "authorization" not in response.text.lower()
