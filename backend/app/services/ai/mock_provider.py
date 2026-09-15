"""
Deterministic, rule-based AI provider. Ported from the frontend demo's
`aiReply()` logic so behavior stays identical while the backend becomes
the source of truth. Zero external calls — safe default for local dev,
grading demos, and offline environments.

Replies follow the requested language (see translations.py): the mock
provider can't lean on an LLM to translate, so it picks from localized
template tables instead of emitting English regardless of `language`.
"""
from app.services.ai.base import AIProvider, AIReply, ChatTurn, WeatherContext
from app.services.ai.translations import (
    MOCK_ROLE_ACTIONS,
    MOCK_TEMPLATES,
    normalize_language,
    translate_condition,
    translate_risk_level,
)

# Keywords in any supported language. Devanagari has no case, so lowering
# only affects the English/latin keywords.
_RAIN_KEYWORDS = ("rain", "flood", "precip", "बारिश", "वर्षा", "बाढ़", "पाऊस", "पावस", "पुरा", "पुराचा")
_HEAT_KEYWORDS = ("hot", "heat", "temperature", "temp", "गर्मी", "तापमान", "गर्म", "उष्णता", "उष्ण")
_SAFETY_KEYWORDS = ("safe", "sos", "shelter", "evacuat", "सुरक्षित", "आश्रय", "निकासी", "निवारा", "आपत्कालीन")

_ROLE_TO_ACTION_KEY = {
    "farmer": "farmer",
    "traveler": "traveler",
    "disaster_management_officer": "officer",
}


class MockAIProvider(AIProvider):
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
        del retrieved, risks  # deterministic provider needs no retrieval/risk detail
        lang = normalize_language(language)
        templates = MOCK_TEMPLATES[lang]
        actions = MOCK_ROLE_ACTIONS[lang]
        msg = message.lower().strip()

        # Role-specific action beats the risk-based one, as before.
        if role in _ROLE_TO_ACTION_KEY:
            action = actions[_ROLE_TO_ACTION_KEY[role]]
        else:
            # 4-level taxonomy; unknown levels degrade to the calm wording.
            action = actions["risk"].get(context.risk_level, actions["risk"]["low"])

        risk_word = translate_risk_level(context.risk_level, lang)
        condition_word = translate_condition(context.condition, lang)
        values = {
            "location": context.location_label,
            "score": f"{context.risk_score:.0f}",
            "rainfall": f"{context.rainfall_mm:.0f}",
            "rain_chance": f"{context.precip_probability_pct:.0f}",
            "temperature": f"{context.temperature_c:.0f}",
            "humidity": f"{context.humidity_pct:.0f}",
            "observed_at": context.observed_at,
            "condition": condition_word,
            "risk_level": risk_word,
            "action": action,
        }

        if any(k in msg for k in _SAFETY_KEYWORDS):
            text = templates["safety"].format(**values)
        elif any(k in msg for k in _RAIN_KEYWORDS):
            text = templates["rain"].format(**values)
        elif any(k in msg for k in _HEAT_KEYWORDS):
            text = templates["heat"].format(**values)
        else:
            text = templates["general"].format(**values)

        if not context.is_verified:
            text += templates["unverified"]

        return AIReply(
            text=text,
            data_used={
                "rainfall_mm": context.rainfall_mm,
                "precip_probability_pct": context.precip_probability_pct,
                "risk_level": context.risk_level,
                "source": context.source,
                "is_verified": context.is_verified,
            },
            language=language,
            provider="mock",
        )
