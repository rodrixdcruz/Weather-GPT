"""
AI provider abstraction.

Every LLM call in the app goes through `AIProvider.generate_reply`, never
directly through an SDK. This means swapping providers (mock -> OpenAI ->
Anthropic -> a fine-tuned in-house model) is a one-line config change
(`AI_PROVIDER` env var) with zero changes to routers or business logic.

IMPORTANT constraint from the product spec: the AI layer must never
invent weather facts. It only reasons over the `WeatherContext` it is
given and must cite what it used. It should never claim an SOS was
dispatched.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WeatherContext:
    """The only weather facts the AI is allowed to reason about.

    Building this from real, provider-sourced data (not the model's own
    knowledge) is what prevents hallucinated forecasts.
    """

    location_label: str
    latitude: float
    longitude: float
    observed_at: str  # ISO timestamp of the forecast/observation
    temperature_c: float
    condition: str
    rainfall_mm: float
    precip_probability_pct: float
    humidity_pct: float
    wind_kph: float
    risk_level: str
    risk_score: float
    hazard_type: str | None
    is_verified: bool
    source: str


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class AIReply:
    text: str
    data_used: dict = field(default_factory=dict)
    language: str = "en"
    provider: str = "unknown"  # which backend answered, e.g. "ollama" / "solar"


class AIProviderError(Exception):
    """Raised when an AI backend cannot produce a reply.

    `kind` is machine-readable (unavailable | model_missing | malformed_response);
    callers use it to degrade gracefully — AI failure must never break
    weather/risk/safety functionality.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class AIProvider(ABC):
    """Implement this for any concrete LLM backend."""

    async def is_available(self) -> bool:
        """Best-effort health check; default True (assume usable)."""
        return True

    @abstractmethod
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
        """Produce a grounded assistant reply.

        Implementations MUST:
        - Only state facts present in `context` (never invent numbers).
        - Respond in `language`.
        - Recommend action framed as guidance, never as a dispatched
          emergency service, unless a real dispatch call actually happened.
        """
        raise NotImplementedError
