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
    APP_NAME: str = "WeatherGPT"
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

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

    # --- Solar Pro 4 (Upstage API, hybrid escalation tier) ---
    # Used ONLY by the "hybrid" provider when the local Ollama model is
    # unavailable/times out or the question needs broader knowledge.
    # SOLAR_API_KEY must stay backend-only: never expose it to the
    # frontend, logs, or API responses.
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
    # free, key-less Open-Meteo API for real observations and forecasts.
    WEATHER_PROVIDER: str = "mock"
    WEATHER_API_KEY: str | None = None  # unused by open_meteo (key-less); kept for future providers
    WEATHER_API_BASE_URL: str | None = None  # override the Open-Meteo endpoint (e.g. a self-hosted mirror)

    # --- Air quality (key-less Open-Meteo Air Quality API, CAMS data) ---
    # Enriches open_meteo readings with US AQI (fueling the AIR_QUALITY
    # risk). Failure-tolerant: AQI problems never break weather. Set false
    # to skip the extra upstream call entirely (e.g. offline demos).
    AIR_QUALITY_ENABLED: bool = True

    # --- Risk engine ---
    # Selects profiles/<name>.json with thresholds, role priorities and
    # guidance templates.
    RISK_PROFILE: str = "default"

    # --- Safety layer ---
    # Provider of OFFICIAL government/authority alerts. "null" ships by
    # default: WeatherGPT then shows ONLY its own derived status, clearly
    # labeled, and never fabricates official alerts.
    SAFETY_ALERT_PROVIDER: str = "null"

    # --- SOS / emergency dispatch ---
    # IMPORTANT: leave disabled until a real dispatch service is wired up.
    # The app must never claim an SOS was sent when this is false.
    SOS_DISPATCH_ENABLED: bool = False
    SOS_DISPATCH_WEBHOOK_URL: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
