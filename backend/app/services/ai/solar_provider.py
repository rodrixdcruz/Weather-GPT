"""
Solar Pro 4 provider (Upstage API) — the hybrid architecture's escalation
tier. OpenAI-compatible /chat/completions endpoint; never the default:
local Ollama is always tried first, and this provider is only consulted
by HybridAIProvider when the local model cannot answer.

Grounding contract (same as every WeatherGPT provider): the model may
only use the structured context it is given. It must never invent
weather numbers, official alerts, or sources.

SECURITY: SOLAR_API_KEY is backend-only. It is sent only in the
Authorization header of the outbound Upstage call and is never logged,
never returned in API responses, and never shipped to the frontend.
"""
import json
import logging

import httpx

from app.core.config import get_settings
from app.services.ai.base import AIProvider, AIProviderError, AIReply, ChatTurn, WeatherContext
from app.services.ai.translations import language_prompt_clause

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are WeatherGPT, a hyperlocal weather-safety assistant.
You answer questions using ONLY the WEATHER CONTEXT, RISK CONTEXT and
RETRIEVED SAFETY GUIDANCE provided below.

Hard rules:
- Never invent or change weather numbers. If a value is not in the context, say it is unavailable.
- Never claim an official government alert or warning exists unless the context says one was provided.
- Never diagnose medical conditions or give medical treatment advice; for health concerns, advise contacting local health services.
- Never invent sources. Only mention the retrieved guidance titles given to you.
- Clearly separate weather FACTS (from the context) from RECOMMENDATIONS.
- If data is incomplete or uncertain, say so plainly.
- For disaster-scale situations, defer to local official authorities.
- Answer in the language requested in the user message. Be concise, calm and actionable.
"""

# Identical grounding contract to the Ollama provider so both tiers answer
# from the same structured context, never from model priors.


class SolarProvider(AIProvider):
    """Talks to the Upstage Solar Pro 4 chat-completions endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.SOLAR_API_KEY
        self._base_url = (base_url or settings.SOLAR_API_BASE_URL).rstrip("/")
        self._model = model or settings.SOLAR_MODEL or "solar-pro4"
        self._timeout = timeout if timeout is not None else settings.SOLAR_TIMEOUT_SECONDS

    async def is_available(self) -> bool:
        """True only when an API key is configured (no ping endpoint)."""
        return bool(self._api_key)

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
        if not self._api_key:
            raise AIProviderError("unavailable", "Solar API key is not configured.")

        prompt = self._build_prompt(message, context, language, retrieved, role, risks)
        try:
            # `_transport` is injectable for tests (httpx.MockTransport); None = normal networking.
            async with httpx.AsyncClient(timeout=self._timeout, transport=getattr(self, "_transport", None)) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            *self._history_messages(history),
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                    },
                )
        except httpx.TimeoutException as exc:
            log.warning("solar.timeout base_url=%s", self._base_url)
            raise AIProviderError("unavailable", "Solar AI did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("solar.unavailable base_url=%s error=%s", self._base_url, type(exc).__name__)
            raise AIProviderError("unavailable", "Solar AI service is not reachable.") from exc

        if response.status_code == 401:
            log.warning("solar.auth_rejected status=401")
            raise AIProviderError("unavailable", "Solar API rejected the credentials.")
        if response.status_code == 404:
            raise AIProviderError("model_missing", f"Solar model '{self._model}' is not available on this endpoint.")
        if response.status_code >= 400:
            log.warning("solar.http_error status=%s", response.status_code)
            raise AIProviderError("unavailable", f"Solar AI returned an error (HTTP {response.status_code}).")

        try:
            data = response.json()
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            log.warning("solar.malformed_response")
            raise AIProviderError("malformed_response", "Solar AI returned an unreadable response.") from exc

        if not text:
            raise AIProviderError("malformed_response", "Solar AI returned an empty response.")

        return AIReply(
            text=text,
            data_used=self._data_used(context, retrieved),
            language=language,
            provider="solar",
        )

    # --- prompt building -------------------------------------------------

    def _build_prompt(
        self,
        message: str,
        context: WeatherContext,
        language: str,
        retrieved: list[dict] | None,
        role: str,
        risks: list | None,
    ) -> str:
        sections = [f"{language_prompt_clause(language)} The user's role is '{role}'."]

        sections.append(
            "WEATHER CONTEXT (the only weather facts allowed):\n"
            + json.dumps(context.__dict__, indent=2)
        )

        if risks:
            risk_lines = [
                {
                    "category": r.category.value,
                    "severity": r.severity.value,
                    "score": r.score,
                    "affected_metric": r.affected_metric,
                    "measured_value": r.measured_value,
                }
                for r in risks
            ]
            sections.append("RISK CONTEXT (detected by the deterministic risk engine):\n" + json.dumps(risk_lines, indent=2))
        else:
            sections.append("RISK CONTEXT: No significant risks detected by the deterministic engine for the configured thresholds.")

        if retrieved:
            blocks = []
            for item in retrieved:
                blocks.append(f"- title: {item.get('title', 'Untitled')}\n  content: {item.get('content', '')}")
            sections.append(
                "RETRIEVED SAFETY GUIDANCE (trusted knowledge base — cite titles if you use them):\n"
                + "\n".join(blocks)
            )
        else:
            sections.append("RETRIEVED SAFETY GUIDANCE: none matched this question.")

        sections.append(f"USER QUESTION: {message}")
        return "\n\n".join(sections)

    @staticmethod
    def _history_messages(history: list[ChatTurn]) -> list[dict]:
        return [{"role": turn.role, "content": turn.content} for turn in history[-6:]]

    @staticmethod
    def _data_used(context: WeatherContext, retrieved: list[dict] | None) -> dict:
        return {
            "rainfall_mm": context.rainfall_mm,
            "precip_probability_pct": context.precip_probability_pct,
            "risk_level": context.risk_level,
            "source": context.source,
            "is_verified": context.is_verified,
            "retrieved_titles": [item.get("title") for item in (retrieved or [])],
        }
