"""
Tests for the escalation FAILOVER chain.

The escalation tier used to be a single free provider: when it hit its rate
limit (the most likely free-tier failure), chat dropped straight to the
data-only fallback. The chain fixes that — providers are tried in order, a
rate-limited provider sits out a cooldown, and the next absorbs the load.

All HTTP is mocked; no real provider is contacted.
"""
import json

import httpx
import pytest

from app.services.ai.base import AIProvider, AIProviderError, ChatTurn, WeatherContext
from app.services.ai.cloud_provider import CloudChatProvider
from app.services.ai.hybrid_provider import EscalationChain, HybridAIProvider
from app.services.ai.presets import (
    KEYED_CHAIN,
    KEYLESS_CHAIN,
    choose_preset_name,
    get_preset,
    resolve_chain_names,
)


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


def _ok(content="chain reply"):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


class _Static(AIProvider):
    """Scripted provider: fails with the given error, else succeeds."""

    def __init__(self, name: str, error: AIProviderError | None = None, text: str = "static ok"):
        self.provider_name = name
        self._error = error
        self._text = text
        self.calls = 0

    async def is_available(self) -> bool:
        return True

    async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return type("R", (), {"text": self._text, "provider": self.provider_name, "language": language, "data_used": {}})()


class TestChainResolution:
    def test_no_chain_configured_resolves_by_key(self):
        """Explicit provider stays single; auto picks a default chain by key."""
        assert resolve_chain_names(provider="groq", providers="", has_api_key=False) == ["groq"]
        assert resolve_chain_names(provider="auto", providers=None, has_api_key=False) == ["ovhcloud"]
        # auto + a configured key = the keyed failover chain, not one provider.
        assert resolve_chain_names(provider="auto", providers=None, has_api_key=True) == ["groq", "ovhcloud"]

    def test_explicit_chain_wins_and_preserves_order(self):
        assert resolve_chain_names(provider="gemini", providers="groq,ovhcloud", has_api_key=False) == ["groq", "ovhcloud"]

    def test_auto_entries_inside_chain_resolve_by_key(self):
        assert resolve_chain_names(provider=None, providers="auto", has_api_key=True) == ["groq"]
        assert resolve_chain_names(provider=None, providers="auto", has_api_key=False) == ["ovhcloud"]

    def test_chain_deduplicates_preserving_order(self):
        assert resolve_chain_names(provider=None, providers="ovhcloud,groq,ovhcloud", has_api_key=False) == ["ovhcloud", "groq"]

    def test_unknown_member_raises_with_valid_options(self):
        with pytest.raises(ValueError) as excinfo:
            resolve_chain_names(provider=None, providers="groq,nope", has_api_key=False)
        assert "ovhcloud" in str(excinfo.value)

    def test_default_chains_are_short_and_keyless_backed(self):
        assert KEYLESS_CHAIN == ["ovhcloud"]
        assert KEYED_CHAIN == ["groq", "ovhcloud"]
        # The chain constants must resolve to real presets.
        for name in [*KEYLESS_CHAIN, *KEYED_CHAIN]:
            get_preset(name)


class TestEscalationChain:
    async def test_first_healthy_provider_serves(self):
        a = _Static("a")
        b = _Static("b")
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: 0.0)

        reply = await chain.generate_reply("rain?", [], _context())

        assert reply.provider == "a"
        assert (a.calls, b.calls) == (1, 0)

    async def test_rate_limited_first_provider_fails_over(self):
        a = _Static("a", error=AIProviderError("rate_limited", "slow down"))
        b = _Static("b")
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: 0.0)

        reply = await chain.generate_reply("rain?", [], _context())

        assert reply.provider == "b"
        assert (a.calls, b.calls) == (1, 1)

    async def test_cooldown_skips_provider_on_later_requests(self):
        now = {"t": 0.0}
        a = _Static("a", error=AIProviderError("rate_limited", "429"))
        b = _Static("b")
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: now["t"])

        await chain.generate_reply("q1", [], _context())
        assert (a.calls, b.calls) == (1, 1)
        assert chain.active_names() == ["b"]

        now["t"] = 30.0  # inside the cooldown window
        await chain.generate_reply("q2", [], _context())
        assert (a.calls, b.calls) == (1, 2), "a must be skipped while cooling down"

        now["t"] = 61.0  # cooldown expired
        a._error = None
        await chain.generate_reply("q3", [], _context())
        assert (a.calls, b.calls) == (2, 2), "a returns to duty after the cooldown"

    async def test_non_rate_limit_errors_fail_over_without_cooldown(self):
        a = _Static("a", error=AIProviderError("unavailable", "down"))
        b = _Static("b")
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: 0.0)

        await chain.generate_reply("q1", [], _context())
        assert chain.active_names() == ["a", "b"], "outages are not rate limits; no cooldown"

        a._error = None
        reply = await chain.generate_reply("q2", [], _context())
        assert reply.provider == "a", "a is retried on the next request"

    async def test_all_fail_raises_last_error_for_the_fallback_path(self):
        a = _Static("a", error=AIProviderError("rate_limited", "429a"))
        b = _Static("b", error=AIProviderError("unavailable", "down"))
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: 0.0)

        with pytest.raises(AIProviderError) as excinfo:
            await chain.generate_reply("q", [], _context())

        assert excinfo.value.detail == "down"  # the last error wins
        assert chain.active_names() == ["b"]

    async def test_all_cooling_raises_actionable_error(self):
        chain = EscalationChain([_Static("a")], cooldown_seconds=60, clock=lambda: 0.0)
        chain._cooldown_until["a"] = 999.0

        with pytest.raises(AIProviderError) as excinfo:
            await chain.generate_reply("q", [], _context())

        assert excinfo.value.kind == "rate_limited"
        assert "cooling down" in excinfo.value.detail

    async def test_unexpected_exception_is_normalized_and_chained(self):
        class _Boom(_Static):
            async def generate_reply(self, *args, **kwargs):
                self.calls += 1
                raise RuntimeError("kaboom")

        a, b = _Boom("a", text="unused"), _Static("b")
        chain = EscalationChain([a, b], cooldown_seconds=60, clock=lambda: 0.0)

        reply = await chain.generate_reply("q", [], _context())

        assert reply.provider == "b"

    async def test_empty_chain_is_rejected(self):
        with pytest.raises(ValueError):
            EscalationChain([], cooldown_seconds=60, clock=lambda: 0.0)

    async def test_is_available_reflects_cooldowns(self):
        chain = EscalationChain([_Static("a")], cooldown_seconds=60, clock=lambda: 0.0)
        assert await chain.is_available() is True
        chain._cooldown_until["a"] = 999.0
        assert await chain.is_available() is False


class TestHybridWiring:
    def _hybrid(self, providers, **settings_overrides):
        from app.services.ai.scope_guard import ScopeGuard

        class _Local(_Static):
            def __init__(self):
                super().__init__("ollama-local")

        return HybridAIProvider(
            primary=_Local(),
            escalation=EscalationChain(providers, cooldown_seconds=60, clock=lambda: 0.0),
            scope_guard=ScopeGuard(),
            **{},
        )

    async def test_broad_knowledge_reaches_the_chain_and_fails_over(self):
        """The user-facing guarantee: a knowledge question answered even when
        the primary free tier is rate-limited."""
        primary = _Static("ovhcloud", error=AIProviderError("rate_limited", "2 req/min per IP"))
        backup = _Static("groq", text="Groq covered it")
        hybrid = self._hybrid([primary, backup])

        reply = await hybrid.generate_reply("Explain El Nino and its effect on rainfall", [], _context())

        assert reply.provider == "groq"
        assert "Groq" in reply.text

    async def test_escalation_properties_report_the_chain(self):
        hybrid = self._hybrid([_Static("a"), _Static("b")])
        assert hybrid.escalation_name == "a"
        assert hybrid.escalation_chain_names == ["a", "b"]
        assert hybrid.escalation_active_names() == ["a", "b"]
        assert len(hybrid.escalation_members) == 2

    async def test_single_escalation_provider_reports_no_chain(self):
        from app.services.ai.scope_guard import ScopeGuard

        hybrid = HybridAIProvider(
            primary=_Static("local"),
            escalation=_Static("only"),
            scope_guard=ScopeGuard(),
        )
        assert hybrid.escalation_name == "only"
        assert hybrid.escalation_chain_names is None


class TestEnvDrivenChain:
    def _provider_with_env(self, monkeypatch, **env):
        from app.core.config import get_settings

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        try:
            from app.services.ai.hybrid_provider import HybridAIProvider

            return HybridAIProvider()._build_default_escalation()
        finally:
            for key in env:
                monkeypatch.delenv(key, raising=False)
            get_settings.cache_clear()

    def test_default_chain_with_groq_key_is_groq_then_keyless(self, monkeypatch):
        chain = self._provider_with_env(
            monkeypatch,
            AI_PROVIDER="hybrid",
            ESCALATION_PROVIDER="auto",
            ESCALATION_PROVIDERS="",
            ESCALATION_API_KEY="free-key",
            ESCALATION_API_KEYS="",
        )
        assert isinstance(chain, EscalationChain)
        assert chain.primary_name == "groq"
        assert [p.provider_name for p in chain.providers] == ["groq", "ovhcloud"]
        # The global key goes to Groq; the keyless member stays keyless.
        groq = chain.providers[0]
        assert groq.has_credentials is True

    def test_keyless_default_is_single_provider(self, monkeypatch):
        chain = self._provider_with_env(
            monkeypatch,
            AI_PROVIDER="hybrid",
            ESCALATION_PROVIDER="auto",
            ESCALATION_PROVIDERS="",
            ESCALATION_API_KEY="",
            ESCALATION_API_KEYS="",
        )
        assert not isinstance(chain, EscalationChain)
        assert chain.provider_name == "ovhcloud"

    def test_explicit_chain_uses_per_provider_keys(self, monkeypatch):
        chain = self._provider_with_env(
            monkeypatch,
            AI_PROVIDER="hybrid",
            ESCALATION_PROVIDER="auto",
            ESCALATION_PROVIDERS="groq,ovhcloud",
            ESCALATION_API_KEY="",
            ESCALATION_API_KEYS='{"groq":"gsk_test"}',
        )
        assert isinstance(chain, EscalationChain)
        groq, ovh = chain.providers
        assert groq.has_credentials is True
        assert ovh.has_credentials is False, "keyless member must not need a key"

    def test_legacy_solar_key_fills_the_solar_member(self, monkeypatch):
        chain = self._provider_with_env(
            monkeypatch,
            AI_PROVIDER="hybrid",
            ESCALATION_PROVIDERS="solar,ovhcloud",
            ESCALATION_API_KEY="",
            ESCALATION_API_KEYS="",
            SOLAR_API_KEY="legacy-solar-key",
        )
        solar = chain.providers[0]
        assert solar.provider_name == "solar"
        assert solar.has_credentials is True


class TestChainRealProviders:
    """Chain members are real CloudChatProviders — the 429 path must work
    through the actual HTTP layer, not just the statics above."""

    async def test_real_429_fails_over_to_real_provider(self):
        def rate_limited(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "slow down"})

        primary = CloudChatProvider(preset=get_preset("groq"), api_key="k")
        primary._transport = httpx.MockTransport(rate_limited)

        backup = CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None)
        backup._transport = httpx.MockTransport(lambda request: _ok("keyless saved the day"))

        chain = EscalationChain([primary, backup], cooldown_seconds=60, clock=lambda: 0.0)
        reply = await chain.generate_reply("rain?", [], _context())

        assert reply.provider == "ovhcloud"
        assert reply.text == "keyless saved the day"

    async def test_provider_without_key_is_skipped_immediately(self):
        """A dormant keyed provider must not waste a turn in the chain."""
        from app.services.ai.base import AIProviderError

        dormant = CloudChatProvider(preset=get_preset("groq"), api_key=None)
        backup = CloudChatProvider(preset=get_preset("ovhcloud"), api_key=None)
        backup._transport = httpx.MockTransport(lambda request: _ok("direct"))

        chain = EscalationChain([dormant, backup], cooldown_seconds=60, clock=lambda: 0.0)
        reply = await chain.generate_reply("rain?", [], _context())

        assert reply.provider == "ovhcloud"
