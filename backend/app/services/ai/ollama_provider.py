"""
Ollama provider: LOCAL, optional LLM backend. Requires a running Ollama
server (https://ollama.com) — nothing paid, nothing cloud. If Ollama is
unavailable or misbehaving, this provider raises AIProviderError and the
chat router degrades gracefully to deterministic built-in guidance. AI
failure must never break weather/risk/safety functionality.

Grounding contract (same as every provider): the model may only use the
structured context it is given. It must never invent weather numbers,
official alerts, or sources.
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


class OllamaProvider(AIProvider):
    """Talks to a local Ollama server's /api/chat endpoint."""

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL or "llama3.2"
        self._timeout = timeout if timeout is not None else settings.OLLAMA_TIMEOUT_SECONDS

    async def is_available(self) -> bool:
        """True if the local Ollama server answers its health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
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
        prompt = self._build_prompt(message, context, language, retrieved, role, risks)
        try:
            # `_transport` is injectable for tests (httpx.MockTransport); None = normal networking.
            async with httpx.AsyncClient(timeout=self._timeout, transport=getattr(self, "_transport", None)) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [{"role": "system", "content": _SYSTEM_PROMPT}, *self._history_messages(history), {"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 120,
                        },
                    },
                )
        except httpx.TimeoutException as exc:
            log.warning("ollama.timeout base_url=%s", self._base_url)
            raise AIProviderError("unavailable", "Local AI did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("ollama.unavailable base_url=%s error=%s", self._base_url, type(exc).__name__)
            raise AIProviderError("unavailable", "Local AI service is not reachable.") from exc

        if response.status_code == 404:
            raise AIProviderError("model_missing", f"Local AI model '{self._model}' is not installed in Ollama.")
        if response.status_code >= 400:
            log.warning("ollama.http_error status=%s", response.status_code)
            raise AIProviderError("unavailable", f"Local AI returned an error (HTTP {response.status_code}).")

        try:
            data = response.json()
            text = str(data["message"]["content"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("ollama.malformed_response")
            raise AIProviderError("malformed_response", "Local AI returned an unreadable response.") from exc

        if not text:
            raise AIProviderError("malformed_response", "Local AI returned an empty response.")

        return AIReply(
            text=text,
            data_used=self._data_used(context, retrieved),
            language=language,
            provider="ollama",
        )

    # --- prompt building ------------------------------------------------

    def _build_prompt(
        self,
        message: str,
        context: WeatherContext,
        language: str,
        retrieved: list[dict] | None,
        role: str,
        risks: list | None,
    ) -> str:
        # Small local models ignore bare codes like 'hi'; naming the spoken
        # language (with its native script) makes compliance far better.
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
