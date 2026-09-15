"""
Hybrid AI provider: local-first two-tier routing.

    Ollama (local, free)  →  Solar Pro 4 (escalation, paid)  →  data fallback

- WeatherGPT-scope questions go to LOCAL Ollama first, always.
- Solar is consulted only when Ollama is unavailable, times out, errors,
  or the router flagged the question as needing broader/general knowledge.
- If both tiers fail, this provider raises AIProviderError transparently,
  and the chat router's existing data-based fallback takes over — that
  path is untouched.
- SIH cost rule: local first. Solar is escalation, never the default.
"""
import logging

from app.services.ai.base import AIProvider, AIProviderError, AIReply, ChatTurn, WeatherContext
from app.services.ai.scope_guard import ScopeVerdict, build_scope_guard

log = logging.getLogger(__name__)


class HybridAIProvider(AIProvider):
    """Chains a primary local provider with the Solar Pro 4 escalation tier."""

    def __init__(
        self,
        primary: AIProvider | None = None,
        escalation: AIProvider | None = None,
        scope_guard=None,
    ) -> None:
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
        from app.services.ai.solar_provider import SolarProvider

        return SolarProvider()

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
        #    either provider (no wasted Ollama load time, no API spend).
        verdict = self._scope_guard.classify(message)
        if verdict is ScopeVerdict.OUT_OF_SCOPE:
            log.info("hybrid.scope_guard out_of_scope")
            return AIReply(
                text=self._scope_guard.refusal_message(language),
                language=language,
                provider="scope_guard",
            )

        # 1. Tier 1: local Ollama — preferred for every in-scope question.
        #    Broad-knowledge flags skip straight to Solar (tier 2), per the
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

        # 2. Tier 2: Solar Pro 4 escalation.
        try:
            reply = await self._escalation.generate_reply(
                message, history, context, language=language, retrieved=retrieved, role=role, risks=risks
            )
            log.info("hybrid.served_by=solar")
            return reply
        except AIProviderError as exc:
            log.warning("hybrid.solar_failed kind=%s detail=%s", exc.kind, exc.detail)
            raise
        except Exception as exc:  # noqa: BLE001 - normalized to the typed error
            log.error("hybrid.solar_unexpected error=%s", type(exc).__name__)
            raise AIProviderError("unavailable", "Both AI tiers failed to answer.") from exc
