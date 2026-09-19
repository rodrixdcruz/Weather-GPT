"""
Example real-LLM provider, using an OpenAI-compatible chat completions API.
Swap AI_PROVIDER=openai and set AI_API_KEY / AI_MODEL to activate this —
no other code changes needed. This same pattern works for Anthropic,
Azure OpenAI, or a self-hosted model by writing a sibling provider class
and registering it in `factory.py`.
"""
import json

import httpx

from app.core.config import get_settings
from app.services.ai.base import AIProvider, AIReply, ChatTurn, WeatherContext
from app.services.ai.translations import language_prompt_clause

_SYSTEM_PROMPT = """You are MausamBagha AI, a disaster-preparedness assistant for India.
Rules:
- ONLY use the weather facts given to you in the context block. Never invent numbers.
- Always state whether the data is VERIFIED or an ESTIMATE.
- Never claim you sent an SOS or contacted emergency services — you only log and inform.
- Respond in the language requested in the user message.
- Be concise, calm, and action-oriented.
"""


class OpenAIProvider(AIProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.AI_API_KEY:
            raise RuntimeError("AI_API_KEY must be set to use the openai provider")
        self._api_key = settings.AI_API_KEY
        self._model = settings.AI_MODEL or "gpt-4o-mini"

    async def generate_reply(
        self,
        message: str,
        history: list[ChatTurn],
        context: WeatherContext,
        language: str = "en",
    ) -> AIReply:
        context_block = json.dumps(context.__dict__, indent=2)
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for turn in history[-10:]:
            messages.append({"role": turn.role, "content": turn.content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{language_prompt_clause(language)}\n\n"
                    f"WEATHER CONTEXT (only source of truth):\n{context_block}\n\n"
                    f"User message: {message}"
                ),
            }
        )

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": messages, "temperature": 0.3},
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        return AIReply(
            text=text,
            data_used={
                "rainfall_mm": context.rainfall_mm,
                "risk_level": context.risk_level,
                "source": context.source,
                "is_verified": context.is_verified,
            },
            language=language,
        )
