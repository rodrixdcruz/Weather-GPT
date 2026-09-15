"""Tests for chat language handling.

The mock AI provider and the router's AI-unavailable fallback must both
answer in the language the client requested (en / hi / mr). LLM providers
(prompt-based) carry their language instruction in
test_ai_and_rag.py-style prompt tests; here we pin the deterministic
paths, which are the ones used by default in local dev.
"""
import pytest

from app.api.v1.routers.chat import _fallback_reply
from app.services.ai.base import AIProvider, AIReply, WeatherContext
from app.services.ai.language_check import is_native_script_reply, reply_matches_language
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.translations import normalize_language, translate_condition, translate_risk_level


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


class TestNormalizeLanguage:
    def test_bare_codes_pass_through(self):
        assert normalize_language("en") == "en"
        assert normalize_language("hi") == "hi"
        assert normalize_language("mr") == "mr"

    def test_bcp47_tags_map_to_base_code(self):
        assert normalize_language("hi-IN") == "hi"
        assert normalize_language("mr-IN") == "mr"

    def test_none_and_junk_degrade_to_english(self):
        assert normalize_language(None) == "en"
        assert normalize_language("") == "en"
        assert normalize_language("xx-UNKNOWN") == "en"

    def test_case_and_whitespace_insensitive(self):
        assert normalize_language(" HI ") == "hi"


class TestMockProviderLanguage:
    @pytest.mark.asyncio
    async def test_hindi_question_gets_hindi_reply(self):
        reply = await MockAIProvider().generate_reply(
            "क्या आज बारिश होगी?", [], _context(risk_level="moderate"), language="hi"
        )
        assert "मिमी" in reply.text
        assert "जोखिम स्तर" in reply.text
        assert "मध्यम" in reply.text

    @pytest.mark.asyncio
    async def test_english_question_still_gets_english_reply(self):
        reply = await MockAIProvider().generate_reply(
            "Will it rain today?", [], _context(), language="en"
        )
        assert "mm" in reply.text
        assert "Risk level is LOW." in reply.text

    @pytest.mark.asyncio
    async def test_marathi_heat_question_gets_marathi_reply(self):
        reply = await MockAIProvider().generate_reply(
            "आज खूप उष्णता आहे का?", [], _context(temperature_c=43.0), language="mr"
        )
        assert "तापमान" in reply.text
        assert "आर्द्रता" in reply.text

    @pytest.mark.asyncio
    async def test_unsupported_language_degrades_to_english(self):
        reply = await MockAIProvider().generate_reply("hello", [], _context(), language="fr")
        assert "Here's the latest" in reply.text

    @pytest.mark.asyncio
    async def test_safety_question_localized(self):
        reply = await MockAIProvider().generate_reply(
            "क्या बाहर जाना सुरक्षित है?", [], _context(risk_level="high"), language="hi"
        )
        assert "SOS" in reply.text
        assert "उच्च" in reply.text

    @pytest.mark.asyncio
    async def test_farmer_role_action_localized(self):
        reply = await MockAIProvider().generate_reply(
            "बारिश होगी?", [], _context(), language="hi", role="farmer"
        )
        assert "खेत" in reply.text

    @pytest.mark.asyncio
    async def test_officer_role_action_localized(self):
        reply = await MockAIProvider().generate_reply(
            "rain?", [], _context(), language="mr", role="disaster_management_officer"
        )
        assert "IMD/NDMA" in reply.text

    @pytest.mark.asyncio
    async def test_extreme_risk_uses_extreme_action_not_calm(self):
        """Regression: 'critical' risk used to fall back to the calm wording."""
        reply = await MockAIProvider().generate_reply(
            "rain?", [], _context(risk_level="extreme"), language="en"
        )
        assert "Move to higher ground" in reply.text

    @pytest.mark.asyncio
    async def test_condition_translated_in_general_reply(self):
        reply = await MockAIProvider().generate_reply("hello", [], _context(), language="hi")
        assert "आंशिक रूप से बादल" in reply.text

    @pytest.mark.asyncio
    async def test_unverified_note_localized(self):
        reply = await MockAIProvider().generate_reply("hello", [], _context(), language="hi")
        assert "मॉडल का अनुमान" in reply.text


class TestFallbackReply:
    def test_english_fallback_unchanged_shape(self):
        text = _fallback_reply("hello", _context(), "customer", "en")
        assert "The AI assistant is unavailable" in text
        assert "Partly cloudy" in text
        assert "LOW" in text

    def test_hindi_fallback(self):
        text = _fallback_reply("hello", _context(), "customer", "hi")
        assert "AI सहायक अभी उपलब्ध नहीं है" in text
        assert "आंशिक रूप से बादल" in text

    def test_marathi_fallback(self):
        text = _fallback_reply("hello", _context(), "customer", "mr")
        assert "AI सहाय्यक सध्या उपलब्ध नाही" in text

    def test_role_specific_fallback_localized(self):
        text = _fallback_reply("hello", _context(), "farmer", "hi")
        assert "खेती से जुड़ा डेटा" in text

    def test_unknown_role_falls_back_to_customer(self):
        text = _fallback_reply("hello", _context(), "wizard", "hi")
        assert "AI सहायक अभी उपलब्ध नहीं है" in text

    def test_emergency_suffix_localized(self):
        text = _fallback_reply("I need help", _context(), "customer", "hi")
        assert "112" in text

    def test_english_emergency_suffix_still_works(self):
        text = _fallback_reply("evacuate now", _context(), "customer", "en")
        assert "112" in text


class TestLanguageDetection:
    """Script-level acceptance: hi and mr share Devanagari, so a native-
    script reply must satisfy BOTH; only wrong-script answers fail.
    Regression guard for the bug where correct Marathi replies were
    detected as 'hi' and replaced with the English fallback."""

    def test_native_script_reply_detected(self):
        assert is_native_script_reply("आज पर्जन्यमान 2 मिमी आहे. धोका पातळी कमी आहे.")
        assert is_native_script_reply("अपेक्षित वर्षा 2 मिमी है। जोखिम स्तर कम है।")

    def test_latin_reply_not_native(self):
        assert not is_native_script_reply("Partly cloudy, 29°C")

    def test_numbers_only_not_native(self):
        assert not is_native_script_reply("29°C, 2 mm")

    def test_empty_not_native(self):
        assert not is_native_script_reply("")

    def test_mixed_devanagari_latin_counts_as_native(self):
        # Real hi/mr text freely mixes English words in.
        assert is_native_script_reply("Mumbai मध्ये आज पाऊस पडेल, weather बदलेल.")

    def test_marathi_reply_accepts_marathi_request(self):
        assert reply_matches_language("पर्जन्यमान 2 मिमी. धोका कमी आहे.", "mr")

    def test_marathi_reply_accepts_hindi_request(self):
        # Same script: a Devanagari reply is intelligible to either.
        assert reply_matches_language("पर्जन्यमान 2 मिमी. धोका कमी आहे.", "hi")

    def test_hindi_reply_accepts_marathi_request(self):
        assert reply_matches_language("अपेक्षित वर्षा 2 मिमी है।", "mr")

    def test_bcp47_tags_accepted(self):
        assert reply_matches_language("पाऊस पडेल.", "mr-IN")
        assert reply_matches_language("बारिश होगी।", "hi-IN")
        assert reply_matches_language("It will rain.", "en-US")

    def test_english_reply_fails_marathi_request(self):
        # The tripwire must still bite: wrong-script answer gets replaced.
        assert not reply_matches_language("Expected rainfall is 2 mm.", "mr")

    def test_english_reply_fails_hindi_request(self):
        assert not reply_matches_language("Expected rainfall is 2 mm.", "hi")

    def test_native_reply_fails_english_request(self):
        assert not reply_matches_language("पर्जन्यमान 2 मिमी.", "en")

    def test_english_reply_passes_english_request(self):
        assert reply_matches_language("Expected rainfall is 2 mm.", "en")


class TestTranslateHelpers:
    def test_translate_condition_known_and_unknown(self):
        assert translate_condition("Partly cloudy", "hi") == "आंशिक रूप से बादल"
        assert translate_condition("Totally made up", "hi") == "Totally made up"
        assert translate_condition("Partly cloudy", "en") == "Partly cloudy"

    def test_translate_risk_level(self):
        assert translate_risk_level("high", "en") == "HIGH"
        assert translate_risk_level("high", "hi") == "उच्च"
        assert translate_risk_level("extreme", "mr") == "अत्यंत"


class TestChatEndpointLanguage:
    @pytest.mark.asyncio
    async def test_chat_hindi_reply_end_to_end(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "क्या आज बारिश होगी?",
                "session_id": "lang-hi-1",
                "language": "hi",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["language"] == "hi"
        assert body["fallback_used"] is False
        assert "मिमी" in body["reply"]

    @pytest.mark.asyncio
    async def test_chat_marathi_reply_end_to_end(self, client, stub_calm_provider):
        """Regression: a correct Marathi reply used to be detected as 'hi',
        trip the mismatch check, and get replaced by the English fallback."""
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "आज पाऊस पडेल का?",
                "session_id": "lang-mr-1",
                "language": "mr",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["fallback_used"] is False, body["reply"]
        assert body["provider"] == "mock"
        # Script-specific content: Marathi reply keeps its own risk word.
        assert "पर्जन्यमान" in body["reply"]
        assert "कमी" in body["reply"]
        assert "could not answer" not in body["reply"]  # no English banner

    @pytest.mark.asyncio
    async def test_chat_wrong_language_reply_gets_replaced(self, client, stub_calm_provider, monkeypatch):
        """The tripwire must still bite: an English answer to a Marathi
        request is replaced by localized data guidance + fallback flag."""
        from app.api.v1.routers import chat as chat_router

        class _EnglishOnly(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="Expected rainfall is 2 mm today.", language=language, provider="ollama")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _EnglishOnly())
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "आज पाऊस पडेल का?",
                "session_id": "lang-mr-wrong-1",
                "language": "mr",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        body = response.json()
        assert body["fallback_used"] is True
        # Replaced reply is the MARATHI data fallback + localized banner.
        assert "AI सहाय्यक सध्या उपलब्ध नाही" in body["reply"]
        assert "तुमच्या निवडलेल्या भाषेत" in body["reply"]
        assert "Expected rainfall is 2 mm today." not in body["reply"]

    @pytest.mark.asyncio
    async def test_chat_english_reply_to_english_request_untouched(self, client, stub_calm_provider, monkeypatch):
        from app.api.v1.routers import chat as chat_router

        class _EnglishOnly(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="Expected rainfall is 2 mm today.", language=language, provider="ollama")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _EnglishOnly())
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "Will it rain today?",
                "session_id": "lang-en-ok-1",
                "language": "en",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        body = response.json()
        assert body["fallback_used"] is False
        assert body["reply"] == "Expected rainfall is 2 mm today."

    @pytest.mark.asyncio
    async def test_chat_hindi_english_mixed_reply_accepted(self, client, stub_calm_provider, monkeypatch):
        """Real hi/mr replies mix English words; script fraction must not
        reject them (boundary: just-under-half Latin letters is fine)."""
        from app.api.v1.routers import chat as chat_router

        class _Mixed(AIProvider):
            async def generate_reply(self, message, history, context, language="en", retrieved=None, role="customer", risks=None):
                return AIReply(text="Mumbai में आज हल्की बारिश, IMDD alert जारी.", language=language, provider="ollama")

        monkeypatch.setattr(chat_router, "get_ai_provider", lambda: _Mixed())
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "क्या आज बारिश होगी?",
                "session_id": "lang-hi-mixed-1",
                "language": "hi",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        body = response.json()
        assert body["fallback_used"] is False
        assert "बारिश" in body["reply"]

    @pytest.mark.asyncio
    async def test_chat_defaults_to_english(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "Will it rain today?",
                "session_id": "lang-en-1",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        body = response.json()
        assert body["language"] == "en"
        assert body["fallback_used"] is False
        assert "mm" in body["reply"]
