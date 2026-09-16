"""
Generic OpenAI-compatible cloud provider — the hybrid architecture's
escalation tier.

Every free provider in `presets.py` (Groq, Gemini, NVIDIA NIM, OpenRouter,
Mistral, keyless OVHcloud) speaks the same /chat/completions dialect, so one
implementation covers all of them and the provider is chosen by config, not
by code. This replaced the Solar-Pro-4-only provider, which was the same
protocol behind a paid key.

Never the default: local Ollama is always tried first, and this provider is
consulted only when the local model cannot answer, or the scope guard flagged
the question as needing broader knowledge than ground-truth weather data.

Grounding contract (same as every WeatherGPT provider): the model may only
use the structured context it is given. It must never invent weather numbers,
official alerts, or sources.

SECURITY: the API key is backend-only. It is sent only in the Authorization
header of the outbound call and is never logged, never returned in API
responses, and never shipped to the frontend.
"""
import json
import logging

import httpx

from app.core.config import get_settings
from app.services.ai.base import AIProvider, AIProviderError, AIReply, ChatTurn, WeatherContext
from app.services.ai.presets import EscalationPreset, choose_preset_name, get_preset
from app.services.ai.translations import language_prompt_clause

log = logging.getLogger(__name__)


class _Unset:
    """Sentinel so an explicit None (\"no key\") is distinct from \"not given\"."""


_UNSET = _Unset()

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


class CloudChatProvider(AIProvider):
    """Talks to any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        *,
        preset: EscalationPreset | None = None,
        provider_name: str | None = None,
        api_key=_UNSET,
        base_url=_UNSET,
        model=_UNSET,
        timeout=_UNSET,
    ) -> None:
        settings = get_settings()
        if preset is None:
            name = choose_preset_name(
                provider=settings.ESCALATION_PROVIDER,
                has_api_key=bool(settings.ESCALATION_API_KEY),
            )
            preset = get_preset(name)

        self._preset = preset
        self.provider_name = provider_name or preset.name
        self._api_key = settings.ESCALATION_API_KEY if api_key is _UNSET else api_key
        resolved_url = settings.ESCALATION_BASE_URL if base_url is _UNSET else base_url
        self._base_url = (resolved_url or preset.base_url).rstrip("/")
        resolved_model = settings.ESCALATION_MODEL if model is _UNSET else model
        self._model = resolved_model or preset.model
        self._timeout = (
            settings.ESCALATION_TIMEOUT_SECONDS if timeout is _UNSET else timeout
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def preset(self) -> EscalationPreset:
        return self._preset

    @property
    def has_credentials(self) -> bool:
        """Whether an API key is present. NOT a validity check.

        Deliberately never returns the key itself — the admin panel is
        allowed to know that a key exists, never what it is.
        """
        return bool(self._api_key)

    async def is_available(self) -> bool:
        """Usable when we have a key, or when the provider needs none.

        There is no cheap ping endpoint across these providers, so this
        reports configuration rather than reachability — the admin panel
        labels it exactly that way.
        """
        return bool(self._api_key) or not self._preset.requires_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
        if self._preset.requires_key and not self._api_key:
            raise AIProviderError(
                "unavailable",
                f"{self._preset.label} requires an API key ({self._preset.signup_url}). "
                f"Set ESCALATION_API_KEY, or use the keyless 'ovhcloud' provider.",
            )

        prompt = self._build_prompt(message, context, language, retrieved, role, risks)
        try:
            # `_transport` is injectable for tests (httpx.MockTransport); None = normal networking.
            async with httpx.AsyncClient(timeout=self._timeout, transport=getattr(self, "_transport", None)) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
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
            log.warning("cloud.timeout provider=%s", self.provider_name)
            raise AIProviderError("unavailable", f"{self._preset.label} did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("cloud.unavailable provider=%s error=%s", self.provider_name, type(exc).__name__)
            raise AIProviderError("unavailable", f"{self._preset.label} is not reachable.") from exc

        if response.status_code == 401:
            log.warning("cloud.auth_rejected provider=%s status=401", self.provider_name)
            raise AIProviderError("unavailable", f"{self._preset.label} rejected the credentials.")
        if response.status_code == 404:
            raise AIProviderError(
                "model_missing",
                f"Model '{self._model}' is not available on {self._preset.label}.",
            )
        if response.status_code == 429:
            # The most likely failure on a free tier, so it gets its own kind
            # and a message that says what to do about it.
            log.warning("cloud.rate_limited provider=%s", self.provider_name)
            raise AIProviderError(
                "rate_limited",
                f"{self._preset.label} rate limit reached ({self._preset.limits}).",
            )
        if response.status_code >= 400:
            log.warning("cloud.http_error provider=%s status=%s", self.provider_name, response.status_code)
            raise AIProviderError(
                "unavailable",
                f"{self._preset.label} returned an error (HTTP {response.status_code}).",
            )

        try:
            data = response.json()
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            log.warning("cloud.malformed_response provider=%s", self.provider_name)
            raise AIProviderError("malformed_response", f"{self._preset.label} returned an unreadable response.") from exc

        if not text:
            raise AIProviderError("malformed_response", f"{self._preset.label} returned an empty response.")

        return AIReply(
            text=text,
            data_used=self._data_used(context, retrieved),
            language=language,
            provider=self.provider_name,
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
