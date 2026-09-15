"""Phase 3 tests: RAG retrieval, Ollama provider, chat grounding/fallback.

All Ollama HTTP is mocked; no local Ollama server is needed for tests.
"""
import httpx
import pytest

from app.services.ai.base import AIProviderError, ChatTurn, WeatherContext
from app.services.ai.factory import get_ai_provider, reset_ai_provider_cache
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.ollama_provider import OllamaProvider
from app.services.ai.rag import RagRetriever


@pytest.fixture
def weather_context():
    return WeatherContext(
        location_label="19.076, 72.878",
        latitude=19.076,
        longitude=72.8777,
        observed_at="2026-09-09T06:00",
        temperature_c=25.0,
        condition="Heavy rain",
        rainfall_mm=68.0,
        precip_probability_pct=92.0,
        humidity_pct=88.0,
        wind_kph=22.0,
        risk_level="high",
        risk_score=47.1,
        hazard_type="rainfall",
        is_verified=True,
        source="open-meteo",
    )


class TestRag:
    def test_retrieves_relevant_documents(self):
        retriever = RagRetriever()
        docs = retriever.retrieve("Should I travel during heavy rain today?")
        assert docs
        titles = [d.title for d in docs]
        assert "Heavy Rain Safety Basics" in titles or "Traveling in Wet Weather" in titles

    def test_farmer_question_retrieves_farming_guidance(self):
        retriever = RagRetriever()
        docs = retriever.retrieve("What should a farmer do about irrigation and field work?")
        assert any("Farm" in d.title for d in docs)

    def test_offtopic_question_returns_empty(self):
        retriever = RagRetriever()
        assert retriever.retrieve("what is 2+2 in maths homework") == []

    def test_retrieval_never_raises(self):
        retriever = RagRetriever(knowledge_path="/nonexistent/path.json")
        assert retriever.retrieve("heavy rain") == []

    def test_documents_carry_title_and_content(self):
        retriever = RagRetriever()
        docs = retriever.retrieve("thunderstorm lightning safety")
        assert docs
        assert all(d.title and d.content for d in docs)

    def test_top_k_respected(self):
        retriever = RagRetriever(top_k=1)
        docs = retriever.retrieve("rain travel farming heat wind storm flood")
        assert len(docs) <= 1


class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_unavailable_server_raises_typed_error(self, weather_context):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        # Point at a closed port via a transport that always fails.
        provider = OllamaProvider(base_url="http://localhost:99999", timeout=1.0)
        provider._transport = httpx.MockTransport(handler)
        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("Is it safe?", [], weather_context)
        assert excinfo.value.kind == "unavailable"

    @pytest.mark.asyncio
    async def test_successful_reply_is_grounded(self, weather_context):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured["messages"] = body["messages"]
            captured["model"] = body["model"]
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "Rainfall is 68 mm; carry rain protection."}})

        provider = OllamaProvider(base_url="http://localhost:11434", model="test-model")
        provider._transport = httpx.MockTransport(handler)
        reply = await provider.generate_reply(
            "Will it rain?",
            [ChatTurn(role="user", content="hi")],
            weather_context,
            retrieved=[{"title": "Heavy Rain Safety Basics", "content": "Avoid waterlogged roads."}],
            role="traveler",
        )
        assert "68 mm" in reply.text
        assert captured["model"] == "test-model"
        # Grounding: the prompt must contain the weather facts + retrieved title + role.
        user_prompt = captured["messages"][-1]["content"]
        assert "rainfall_mm" in user_prompt
        assert "Heavy Rain Safety Basics" in user_prompt
        assert "traveler" in user_prompt
        assert reply.data_used["retrieved_titles"] == ["Heavy Rain Safety Basics"]

    @pytest.mark.asyncio
    async def test_http_404_maps_to_model_missing(self, weather_context):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "model not found"})

        provider = OllamaProvider(base_url="http://localhost:11434")
        provider._transport = httpx.MockTransport(handler)
        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("hello", [], weather_context)
        assert excinfo.value.kind == "model_missing"

    @pytest.mark.asyncio
    async def test_malformed_json_maps_to_malformed_response(self, weather_context):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        provider = OllamaProvider(base_url="http://localhost:11434")
        provider._transport = httpx.MockTransport(handler)
        with pytest.raises(AIProviderError) as excinfo:
            await provider.generate_reply("hello", [], weather_context)
        assert excinfo.value.kind == "malformed_response"


import json  # noqa: E402  (used inside handlers above)


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_returns_structured_grounded_response(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "Will it rain today?",
                "session_id": "test-session-1",
                "latitude": 19.076,
                "longitude": 72.8777,
                "role": "farmer",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["reply"]
        assert body["role"] == "farmer"
        assert body["fallback_used"] is False  # mock AI answers; fallback only when the AI backend fails
        assert isinstance(body["risks"], list)
        assert body["weather"]["temperature_c"] == 29.0
        assert body["data_used"]["source"] == "test"

    @pytest.mark.asyncio
    async def test_chat_retrieves_sources_for_rain_question(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "Is it safe to travel in heavy rain?",
                "session_id": "test-session-2",
                "latitude": 19.076,
                "longitude": 72.8777,
            },
        )
        body = response.json()
        assert isinstance(body["sources"], list)

    @pytest.mark.asyncio
    async def test_chat_invalid_role_normalized(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "hello",
                "session_id": "test-session-3",
                "latitude": 19.076,
                "longitude": 72.8777,
                "role": "wizard",
            },
        )
        assert response.json()["role"] == "customer"

    @pytest.mark.asyncio
    async def test_chat_validates_coordinates(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "hello",
                "session_id": "test-session-4",
                "latitude": 200,
                "longitude": 0,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_message_required(self, client, stub_calm_provider):
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "", "session_id": "s", "latitude": 0, "longitude": 0},
        )
        assert response.status_code == 422


class TestFactoryOllama:
    def test_factory_selects_ollama(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        from app.core.config import get_settings

        get_settings.cache_clear()
        reset_ai_provider_cache()
        try:
            assert type(get_ai_provider()).__name__ == "OllamaProvider"
        finally:
            get_settings.cache_clear()
            monkeypatch.delenv("AI_PROVIDER", raising=False)
            get_settings.cache_clear()
            reset_ai_provider_cache()
