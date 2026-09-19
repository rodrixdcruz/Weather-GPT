"""
Central app configuration, loaded entirely from environment variables.
Never hardcode API keys, DB URLs, or provider names — this is the one
place that reads them.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "MausamBagha AI"
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    # Browser origins allowed to call this API. Development default; a
    # deployment MUST set the real frontend origin (e.g.
    # CORS_ORIGINS='["https://weathergpt.example.com"]'). When the frontend is
    # served behind the nginx image the SPA calls /api/ on its own origin, so
    # requests are same-origin and CORS is not exercised at all.
    CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://weather-gpt-beryl.vercel.app",
    "https://weather-gpt-prjkpmxy3-rodrixdcruz.vercel.app",
    "https://weather-gpt-k3435ehbw-rodrixdcruz.vercel.app",
]
    # Interactive API docs (/docs, /redoc, /openapi.json). Enabled by default so
    # local development keeps them; production sets DOCS_ENABLED=false so the
    # full route surface (including /admin/*) is not advertised publicly.
    # Endpoint paths and behaviour are unchanged either way.
    DOCS_ENABLED: bool = True

    # --- Database (PostgreSQL) ---
    DATABASE_URL: str = "postgresql+psycopg://weathergpt:weathergpt@localhost:5432/weathergpt"

    # --- AI provider abstraction ---
    # "mock" works with zero configuration for local/demo use.
    # "ollama" uses a LOCAL Ollama server (optional, free, no cloud).
    # "hybrid" = Ollama first, Solar Pro 4 escalation on failure (see below).
    # Swap providers by changing this env var only — no application code
    # should need to change. AI is never required: weather/risk/safety
    # work fully without it.
    AI_PROVIDER: str = "mock"
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None

    # --- Escalation tier (hybrid provider's second model) ---
    # Used ONLY by the "hybrid" provider, when the local Ollama model is
    # unavailable/times out or the question needs broader knowledge.
    #
    # Any OpenAI-compatible chat-completions endpoint works. The named
    # providers in services/ai/presets.py all have PERMANENT FREE TIERS, so
    # this tier needs no budget:
    #   "auto"      (default) - Groq when ESCALATION_API_KEY is set,
    #                           otherwise the keyless OVHcloud endpoint
    #   "groq" | "gemini" | "nvidia" | "openrouter" | "mistral"  (free, keyed)
    #   "ovhcloud"  - free and KEYLESS (no signup at all)
    #   "solar"     - the previous paid tier, still supported
    # ESCALATION_API_KEY must stay backend-only: never expose it to the
    # frontend, logs, or API responses.
    ESCALATION_PROVIDER: str = "auto"
    # Optional ordered failover chain for the escalation tier, e.g.
    # "groq,ovhcloud" (try Groq, then the keyless OVHcloud tier on any
    # failure including rate limits). Comma-separated preset names;
    # "auto" entries resolve like ESCALATION_PROVIDER would. Empty = the
    # single provider chosen by ESCALATION_PROVIDER (no failover).
    ESCALATION_PROVIDERS: str = ""
    # After a provider fails with a rate limit, skip it for this many seconds
    # so later requests try the next provider (or the data fallback)
    # immediately instead of waiting for the 429 again.
    ESCALATION_COOLDOWN_SECONDS: float = 65.0
    ESCALATION_API_KEY: str | None = None
    # Per-provider keys as a JSON map string, e.g. '{"groq": "gsk_..."}'.
    # Deliberately a plain str: pydantic-settings (2.5.x) decodes complex
    # env values as JSON *before* field validators run, so a dict-typed
    # field would crash startup on the blank value a compose passthrough
    # (${VAR:-}) produces. Parsed in hybrid_provider._per_provider_keys().
    ESCALATION_API_KEYS: str = ""

    ESCALATION_MODEL: str | None = None  # None = the preset's default model (applies to every chain member)
    ESCALATION_BASE_URL: str | None = None  # None = the preset's default URL (applies to every chain member)
    ESCALATION_TIMEOUT_SECONDS: float = 30.0

    # --- Solar Pro 4 (Upstage API) — legacy escalation credentials ---
    # Read only when ESCALATION_PROVIDER=solar, so an existing key keeps
    # working. Solar is no longer the default escalation tier.
    SOLAR_API_KEY: str | None = None
    SOLAR_MODEL: str = "solar-pro4"
    SOLAR_API_BASE_URL: str = "https://api.upstage.ai/v1/solar"
    SOLAR_TIMEOUT_SECONDS: float = 30.0

    # --- Ollama (local AI, optional) ---
    # If the server is not running, chat falls back to deterministic
    # built-in guidance — nothing else in the app is affected.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_TIMEOUT_SECONDS: float = 120.0

    # --- Local RAG (retrieval over trusted knowledge base) ---
    RAG_ENABLED: bool = True
    RAG_TOP_K: int = 3
    RAG_KNOWLEDGE_DIR: str | None = None  # override the built-in knowledge base

    # --- Weather data provider abstraction ---
    # "mock" ships fixture data for demo/offline use; "open_meteo" uses the
    # free, key-less Open-Meteo API for real observations and forecasts;
    # "met_norway" uses MET Norway's free, key-less Locationforecast API —
    # preferred on cloud platforms because Open-Meteo blocks shared cloud
    # egress IPs (observed 429 on Render) while MET Norway does not.
    WEATHER_PROVIDER: str = "mock"
    WEATHER_API_KEY: str | None = None  # unused by open_meteo (key-less); kept for future providers
    WEATHER_API_BASE_URL: str | None = None  # override the Open-Meteo endpoint (e.g. a self-hosted mirror)

    # --- Air quality (key-less Open-Meteo Air Quality API, CAMS data) ---
    # Enriches open_meteo readings with US AQI (fueling the AIR_QUALITY
    # risk). Failure-tolerant: AQI problems never break weather. Set false
    # to skip the extra upstream call entirely (e.g. offline demos).
    AIR_QUALITY_ENABLED: bool = True

    # --- Road routing proxy (FOSSGIS OSRM, key-less) ---
    # The backend proxies route/travel-time lookups so ALL visitors share one
    # server-side cache and FOSSGIS sees a single well-behaved client instead
    # of uncoordinated public traffic. Override to point at a self-hosted OSRM.
    ROUTING_OSRM_BASE_URL: str | None = None

    # --- Risk engine ---
    # Selects profiles/<name>.json with thresholds, role priorities and
    # guidance templates.
    RISK_PROFILE: str = "default"

    # --- Safety layer ---
    # Provider of OFFICIAL government/authority alerts. "null" ships by
    # default: MausamBagha AI then shows ONLY its own derived status, clearly
    # labeled, and never fabricates official alerts.
    SAFETY_ALERT_PROVIDER: str = "null"

    # --- Auth / dashboard sessions ---
    # Accounts live in the database and are seeded on startup when missing.
    # CHANGE THESE for anything beyond a local demo. Secrets stay in env
    # vars (.env) — never in code or the frontend.
    AUTH_ENABLED: bool = True
    AUTH_SESSION_TTL_HOURS: int = 12
    AUTH_ADMIN_USERNAME: str = "admin"
    AUTH_ADMIN_PASSWORD: str = "admin123"
    AUTH_ADMIN_DISPLAY_NAME: str = "Operations Admin"
    AUTH_DEMO_USERNAME: str = "demo"
    AUTH_DEMO_PASSWORD: str = "demo123"
    AUTH_DEMO_DISPLAY_NAME: str = "Demo User"
    # Judge/hackathon account: same citizen view as demo, but the dashboard
    # auto-opens the guided feature tour. Change the password for any deploy
    # the judges can reach; set AUTH_JUDGE_ENABLED=false to disable seeding.
    AUTH_JUDGE_ENABLED: bool = True
    AUTH_JUDGE_USERNAME: str = "judge"
    AUTH_JUDGE_PASSWORD: str = "judge123"
    AUTH_JUDGE_DISPLAY_NAME: str = "Judge"
    # Create the tables + seed accounts automatically at startup (idempotent).
    # Never fatal: if the database is down the API still serves weather/risk.
    AUTH_AUTO_INIT_DB: bool = True

    # --- SOS / emergency dispatch ---
    # IMPORTANT: leave disabled until a real dispatch service is wired up.
    # The app must never claim an SOS was sent when this is false.
    SOS_DISPATCH_ENABLED: bool = False
    SOS_DISPATCH_WEBHOOK_URL: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
