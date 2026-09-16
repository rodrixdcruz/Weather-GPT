"""
Hybrid AI provider: local-first two-tier routing.

    Ollama (local, free)  →  free cloud escalation tier  →  data fallback

- WeatherGPT-scope questions go to LOCAL Ollama first, always.
- The cloud tier is consulted only when Ollama is unavailable, times out,
  errors, or the scope guard flagged the question as needing broader/general
  knowledge than ground-truth weather data.
- If both tiers fail, this provider raises AIProviderError transparently,
  and the chat router's existing data-based fallback takes over — that
  path is untouched.
- Cost rule: local first, always. The escalation tier is now FREE providers
  (see presets.py) — keyless or free-tier-keyed — so escalation never means
  a bill. It is still escalation, never the default: an in-scope question
  never spends a cloud request while the local model is healthy.
- Failover: the escalation tier is an ORDERED CHAIN of free providers. When
  one is rate-limited or unreachable, the next is tried, so a single 429 no
  longer drops the user to the data-only fallback. Rate-limited providers
  sit out a short cooldown afterwards (a 429 will not recover before the
  window resets; retrying early just burns latency every request).
"""
import json
import logging
import time

from app.services.ai.base import AIProvider, AIProviderError, AIReply, ChatTurn, WeatherContext
from app.services.ai.scope_guard import ScopeVerdict, build_scope_guard

log = logging.getLogger(__name__)


class EscalationChain(AIProvider):
    """Ordered free providers tried in sequence (names from presets.py).

    The first provider is the configured escalation tier; the rest absorb its
    failures. Any AIProviderError moves the attempt to the next provider; a
    rate limit additionally puts that provider on cooldown, so subsequent
    requests skip straight past it until the window resets.

    State lives on the singleton built by the factory, so cooldowns persist
    across requests. The clock is injectable for tests.
    """

    def __init__(
        self,
        providers: list[AIProvider],
        cooldown_seconds: float = 65.0,
        clock=time.monotonic,
    ) -> None:
        if not providers:
            raise ValueError("EscalationChain needs at least one provider.")
        self._providers = providers
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._cooldown_until: dict[str, float] = {}

    @staticmethod
    def _name(provider: AIProvider) -> str:
        return getattr(provider, "provider_name", None) or type(provider).__name__

    @property
    def providers(self) -> list[AIProvider]:
        return list(self._providers)

    @property
    def primary_name(self) -> str:
        return self._name(self._providers[0])

    def active_names(self) -> list[str]:
        """Chain order minus providers currently on cooldown (for the panel)."""
        now = self._clock()
        return [self._name(p) for p in self._providers if self._cooldown_until.get(self._name(p), 0.0) <= now]

    def _on_cooldown(self, name: str) -> bool:
        return self._cooldown_until.get(name, 0.0) > self._clock()

    async def is_available(self) -> bool:
        for provider in self._providers:
            if not self._on_cooldown(self._name(provider)) and await provider.is_available():
                return True
        return False

    async def generate_reply(
        self,
        message: str,
        history: list[ChatTurn],
        context: WeatherContext,
        language: str = "en",
        retrieved: list[dict] | None = None,
        role: str = "customer",
        risks: list | None = None,
    ) -> AIReply:
        last_error: AIProviderError | None = None
        attempted = 0
        for provider in self._providers:
            name = self._name(provider)
            if self._on_cooldown(name):
                log.info("escalation.chain.skip name=%s reason=cooldown", name)
                continue
            if not await provider.is_available():
                # A keyed provider without its key is skipped without a turn.
                log.info("escalation.chain.skip name=%s reason=not_configured", name)
                continue
            attempted += 1
            try:
                reply = await provider.generate_reply(
                    message, history, context, language=language, retrieved=retrieved, role=role, risks=risks
                )
                if attempted > 1:
                    log.warning("escalation.chain.failover_served served_by=%s", name)
                return reply
            except AIProviderError as exc:
                if exc.kind == "rate_limited":
                    self._cooldown_until[name] = self._clock() + self._cooldown_seconds
                    log.warning(
                        "escalation.chain.cooldown provider=%s seconds=%.0f", name, self._cooldown_seconds
                    )
                log.warning(
                    "escalation.chain.provider_failed provider=%s kind=%s detail=%s",
                    name, exc.kind, exc.detail,
                )
                last_error = exc
            except Exception as exc:  # noqa: BLE001 - one broken link must not kill the chain
                log.error("escalation.chain.provider_unexpected provider=%s error=%s", name, type(exc).__name__)
                last_error = AIProviderError("unavailable", f"{name} failed unexpectedly.")

        if last_error is not None:
            raise last_error
        if all(self._on_cooldown(self._name(p)) for p in self._providers):
            raise AIProviderError(
                "rate_limited",
                "All escalation providers are cooling down after rate limits; try again shortly.",
            )
        raise AIProviderError(
            "unavailable",
            "No escalation provider is configured — set ESCALATION_API_KEY or use the keyless 'ovhcloud' tier.",
        )


class HybridAIProvider(AIProvider):
    """Chains the primary local provider with a free cloud escalation tier."""

    def __init__(
        self,
        primary: AIProvider | None = None,
        escalation: AIProvider | None = None,
        scope_guard=None,
    ) -> None:
        settings = None
        if primary is None or escalation is None or scope_guard is None:
            from app.core.config import get_settings

            settings = get_settings()
        self._primary = primary if primary is not None else self._build_default_primary()
        self._escalation = escalation if escalation is not None else self._build_default_escalation()
        self._scope_guard = scope_guard if scope_guard is not None else build_scope_guard(settings)

    @staticmethod
    def _build_default_primary() -> AIProvider:
        from app.services.ai.ollama_provider import OllamaProvider

        return OllamaProvider()

    @staticmethod
    def _build_default_escalation() -> AIProvider:
        """The configured FREE escalation chain (see services/ai/presets.py).

        One provider behaves exactly as before. With ESCALATION_PROVIDERS set
        — or a free key plus the keyless tier under "auto" — the extra
        providers absorb rate limits and outages instead of dropping the
        user to the data fallback.
        """
        from app.core.config import get_settings
        from app.services.ai.cloud_provider import CloudChatProvider
        from app.services.ai.presets import get_preset, resolve_chain_names

        settings = get_settings()
        names = resolve_chain_names(
            provider=settings.ESCALATION_PROVIDER,
            providers=settings.ESCALATION_PROVIDERS,
            has_api_key=bool(settings.ESCALATION_API_KEY),
        )
        # Per-provider keys win. ESCALATION_API_KEYS is a JSON map string
        # ({"groq": "..."}); the single global ESCALATION_API_KEY goes to the
        # first key-needing provider without one (legacy: Solar's own var).
        keys: dict[str, str] = {}
        raw_keys = (settings.ESCALATION_API_KEYS or "").strip()
        if raw_keys:
            try:
                parsed = json.loads(raw_keys)
                if not isinstance(parsed, dict):
                    raise ValueError("must be a JSON object")
                keys = {str(k): str(v) for k, v in parsed.items() if str(v).strip()}
            except ValueError as exc:
                log.warning("escalation.keys.invalid detail=%s — ignoring per-provider keys", exc)
        for name in names:
            if get_preset(name).requires_key and not keys.get(name):
                legacy = settings.SOLAR_API_KEY if name == "solar" else None
                keys[name] = legacy or settings.ESCALATION_API_KEY or ""
                break
        providers = [
            CloudChatProvider(preset=get_preset(name), api_key=keys.get(name) or None)
            for name in names
        ]
        if len(providers) == 1:
            return providers[0]
        return EscalationChain(providers, cooldown_seconds=settings.ESCALATION_COOLDOWN_SECONDS)

    @property
    def escalation_name(self) -> str:
        """The escalation tier's primary provider, for logs and the admin panel."""
        if isinstance(self._escalation, EscalationChain):
            return self._escalation.primary_name
        return getattr(self._escalation, "provider_name", None) or type(self._escalation).__name__

    @property
    def escalation_chain_names(self) -> list[str] | None:
        """Full failover order, or None when no chain is configured."""
        if isinstance(self._escalation, EscalationChain):
            return [getattr(p, "provider_name", type(p).__name__) for p in self._escalation.providers]
        return None

    @property
    def escalation_members(self) -> list[AIProvider]:
        """Every provider in the escalation tier, primary first."""
        if isinstance(self._escalation, EscalationChain):
            return self._escalation.providers
        return [self._escalation]

    def escalation_active_names(self) -> list[str]:
        """Chain members not currently on cooldown, for the admin panel."""
        if isinstance(self._escalation, EscalationChain):
            return self._escalation.active_names()
        return [self.escalation_name]

    async def is_available(self) -> bool:
        """Usable when either tier can answer."""
        if await self._primary.is_available():
            return True
        return await self._escalation.is_available()

    async def generate_reply(
        self,
        message: str,
        history: list[ChatTurn],
        context: WeatherContext,
        language: str = "en",
        retrieved: list[dict] | None = None,
        role: str = "customer",
        risks: list | None = None,
    ) -> AIReply:
        # 0. Scope guard: obvious nonsense / off-topic input never reaches
        #    either provider (no wasted Ollama load time, no cloud request).
        verdict = self._scope_guard.classify(message)
        if verdict is ScopeVerdict.OUT_OF_SCOPE:
            log.info("hybrid.scope_guard out_of_scope")
            return AIReply(
                text=self._scope_guard.refusal_message(language),
                language=language,
                provider="scope_guard",
            )

        # 1. Tier 1: local Ollama — preferred for every in-scope question.
        #    Broad-knowledge flags skip straight to the cloud tier, per the
        #    escalation contract; everything else tries local first.
        if verdict is not ScopeVerdict.BROAD_KNOWLEDGE:
            try:
                reply = await self._primary.generate_reply(
                    message, history, context, language=language, retrieved=retrieved, role=role, risks=risks
                )
                log.info("hybrid.served_by=ollama")
                return reply
            except AIProviderError as exc:
                # Distinguish clean escalation triggers from unexpected bugs
                # (which still escalate, but loudly).
                log.warning("hybrid.ollama_failed kind=%s detail=%s", exc.kind, exc.detail)
            except Exception as exc:  # noqa: BLE001 - a broken tier must not kill the chain
                log.error("hybrid.ollama_unexpected error=%s", type(exc).__name__)

        # 2. Tier 2: free cloud escalation — an ordered chain of free
        #    providers; the next one absorbs a rate limit or outage.
        name = self.escalation_name
        try:
            reply = await self._escalation.generate_reply(
                message, history, context, language=language, retrieved=retrieved, role=role, risks=risks
            )
            # Log WHO answered, not who was first in the chain: on a failover
            # the primary is not the server, and a misleading served_by makes
            # rate-limit debugging point at the wrong provider.
            log.info("hybrid.served_by=%s", reply.provider)
            return reply
        except AIProviderError as exc:
            log.warning("hybrid.escalation_failed provider=%s kind=%s detail=%s", name, exc.kind, exc.detail)
            raise
        except Exception as exc:  # noqa: BLE001 - normalized to the typed error
            log.error("hybrid.escalation_unexpected provider=%s error=%s", name, type(exc).__name__)
            raise AIProviderError("unavailable", "Both AI tiers failed to answer.") from exc
