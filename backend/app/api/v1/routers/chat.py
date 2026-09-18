import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import effective_role, optional_session
from app.core.logging import get_logger
from app.models.models import LoginSession
from app.services.ai.metrics import get_metrics
from app.schemas.schemas import ChatRequest, ChatResponse
from app.services.ai.base import ChatTurn, WeatherContext, AIProviderError
from app.services.ai.factory import get_ai_provider
from app.services.ai.language_check import reply_matches_language
from app.services.ai.rag import get_retriever
from app.services.ai.scope_guard import ScopeVerdict, build_scope_guard
from app.services.ai.translations import (
    DEFAULT_LANGUAGE,
    EMERGENCY_KEYWORDS,
    FALLBACK_EMERGENCY_SUFFIX,
    FALLBACK_TEMPLATES,
    LANGUAGE_MISMATCH_NOTICES,
    normalize_language,
    translate_condition,
    translate_risk_level,
)
from app.services.risk.engine import RiskEngine
from app.services.risk.roles import normalize_role
from app.services.weather.base import WeatherProviderError
from app.services.weather.factory import get_weather_provider, resolve_demo_scenario

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger(__name__)

# NOTE: in-memory demo history only. Replace with ChatMessage rows in
# Postgres (see models/models.py) for real session persistence.
_HISTORY: dict[str, list[ChatTurn]] = {}

# Shared scope guard: obvious nonsense/off-topic input never reaches any
# AI provider (protects the free local model AND the paid escalation).
_scope_guard = build_scope_guard()

# Shown verbatim to the user when AI generation fails, so the answer is
# still grounded in the actual weather/risk data for their question.
# Localized per requested language; see services/ai/translations.py.
_FALLBACK_BY_ROLE = FALLBACK_TEMPLATES


def _fallback_reply(message: str, context: WeatherContext, role: str, language: str = DEFAULT_LANGUAGE) -> str:
    lang = normalize_language(language)
    lang_templates = _FALLBACK_BY_ROLE.get(lang) or _FALLBACK_BY_ROLE[DEFAULT_LANGUAGE]
    template = lang_templates.get(role) or lang_templates["customer"]
    text = template.format(
        condition=translate_condition(context.condition, lang),
        temperature=context.temperature_c,
        rainfall=context.rainfall_mm,
        humidity=context.humidity_pct,
        wind=context.wind_kph,
        risk_level=translate_risk_level(context.risk_level, lang),
        risk_score=context.risk_score,
    )
    if any(k in message.lower() for k in EMERGENCY_KEYWORDS):
        text += FALLBACK_EMERGENCY_SUFFIX[lang]
    return text


@router.post("/send", response_model=ChatResponse)
async def send_chat_message(payload: ChatRequest, session: LoginSession | None = Depends(optional_session)):
    started = time.perf_counter()
    # 1. Weather context (never fabricated — provider errors surface cleanly).
    # Scenario simulation is judge-only: other sessions silently get live data.
    scenario = resolve_demo_scenario(payload.scenario, session)
    provider = get_weather_provider(scenario=scenario, judge=scenario != "normal")
    try:
        reading = await provider.get_current(payload.latitude, payload.longitude)
    except WeatherProviderError as exc:
        from app.api.v1.routers.weather import _provider_http_error

        raise _provider_http_error(exc) from None

    # 2. Deterministic risk assessment for the active role. A signed-in
    #    session owns the role (it was chosen once at login), so the client
    #    cannot re-select a role mid-session.
    active_role = normalize_role(effective_role(payload.role, session))
    assessment = RiskEngine().assess(reading, role=active_role)
    top = assessment.risks[0] if assessment.risks else None
    risk_level = top.severity.value if top else "low"
    risk_score = top.score if top else 0.0
    hazard_type = top.category.value if top else None

    context = WeatherContext(
        location_label=reading.location_label,
        latitude=reading.latitude,
        longitude=reading.longitude,
        observed_at=reading.observed_at,
        temperature_c=reading.temperature_c,
        condition=reading.condition,
        rainfall_mm=reading.rainfall_mm,
        precip_probability_pct=reading.precip_probability_pct,
        humidity_pct=reading.humidity_pct,
        wind_kph=reading.wind_kph,
        risk_level=risk_level,
        risk_score=risk_score,
        hazard_type=hazard_type,
        is_verified=reading.is_verified,
        source=reading.source,
    )

    # 2.5. Scope guard: refuse obvious nonsense/off-topic input without
    #      burning an Ollama cold-start or a paid Solar call. Runs before
    #      RAG/LLM work; the reply is localized and marked provider=
    #      "scope_guard". The hybrid provider re-checks internally (harmless
    #      double classification, one cheap regex pass) so its broad-
    #      knowledge escalation flag still works when this router-level
    #      guard passes a borderline message through.
    if _scope_guard.classify(payload.message) is ScopeVerdict.OUT_OF_SCOPE:
        log.info("chat.scope_guard session=%s out_of_scope", payload.session_id)
        get_metrics().record_reply(
            provider="scope_guard",
            fallback_used=False,
            role=active_role,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return ChatResponse(
            reply=_scope_guard.refusal_message(payload.language),
            data_used={},
            language=payload.language,
            role=active_role,
            fallback_used=False,
            provider="scope_guard",
            sources=[],
            weather=context.__dict__,
            risks=[dict(r.__dict__) for r in assessment.risks],
        )

    # 3. RAG retrieval over the trusted knowledge base (failure-tolerant).
    retrieved = []
    if payload.rag_enabled:
        retriever = get_retriever()
        retrieved = retriever.retrieve(payload.message)
        log.info("chat.rag session=%s retrieved=%d titles=%s", payload.session_id, len(retrieved), [d.title for d in retrieved])

    # 4. AI generation with graceful degradation. AI failure must never
    #    break the chat — we answer from real data instead.
    history = _HISTORY.setdefault(payload.session_id, [])
    ai = get_ai_provider()
    fallback_used = False
    answered_by = "fallback"
    sources = [d.title for d in retrieved]
    try:
        reply = await ai.generate_reply(
            payload.message,
            history,
            context,
            language=payload.language,
            retrieved=[dict(d) for d in retrieved],
            role=active_role,
            risks=assessment.risks,
        )
        answer = reply.text
        answered_by = reply.provider
    except AIProviderError as exc:
        log.warning("chat.ai_fallback kind=%s detail=%s", exc.kind, exc.detail)
        answer = _fallback_reply(payload.message, context, active_role, payload.language)
        fallback_used = True
    except Exception as exc:  # noqa: BLE001 - AI must never 500 the chat
        log.error("chat.ai_unexpected_error error=%s", type(exc).__name__)
        answer = _fallback_reply(payload.message, context, active_role, payload.language)
        fallback_used = True

    # A reply in the wrong language is as broken as no reply: surface it
    # when the provider answered but ignored the requested language.
    # Script-level check: hi and mr share Devanagari, so a native-script
    # reply satisfies either; only wrong-script (e.g. English) answers are
    # replaced. Skipped when the data fallback already produced the answer.
    if not fallback_used and not reply_matches_language(answer, payload.language):
        log.warning("chat.language_mismatch requested=%s session=%s", payload.language, payload.session_id)
        lang = normalize_language(payload.language)
        answer = _fallback_reply(payload.message, context, active_role, payload.language) + "\n\n" + LANGUAGE_MISMATCH_NOTICES.get(
            lang, LANGUAGE_MISMATCH_NOTICES[DEFAULT_LANGUAGE]
        )
        fallback_used = True

    history.append(ChatTurn(role="user", content=payload.message))
    history.append(ChatTurn(role="assistant", content=answer))
    if len(history) > 20:
        del _HISTORY[payload.session_id]
        _HISTORY[payload.session_id] = history[-20:]

    latency_ms = (time.perf_counter() - started) * 1000
    log.info("chat.send session=%s role=%s risk=%s fallback=%s latency_ms=%.0f", payload.session_id, active_role, risk_level, fallback_used, latency_ms)

    # Model observability for the admin panel: who answered, how often we
    # had to fall back to deterministic data answers, and how slow it was.
    metrics = get_metrics()
    metrics.record_reply(
        provider=answered_by,
        fallback_used=fallback_used,
        role=active_role,
        latency_ms=latency_ms,
    )
    if fallback_used and answered_by == "fallback":
        metrics.record_error(kind="both_tiers_failed", detail="Answered from weather data instead of a model.")

    return ChatResponse(
        reply=answer,
        data_used={
            "rainfall_mm": context.rainfall_mm,
            "precip_probability_pct": context.precip_probability_pct,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "hazard_type": hazard_type,
            "source": context.source,
            "is_verified": context.is_verified,
        },
        provider=answered_by,
        language=payload.language,
        role=active_role,
        fallback_used=fallback_used,
        sources=sources,
        weather=context.__dict__,
        risks=[dict(r.__dict__) for r in assessment.risks],
    )
