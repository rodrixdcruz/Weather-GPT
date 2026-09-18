from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AirQualityOut(BaseModel):
    """Normalized air quality attached to a weather reading (when available).

    from_attributes lets routers build it straight from the AirQuality
    dataclass inside WeatherReading.__dict__.
    """

    model_config = ConfigDict(from_attributes=True)

    observed_at: str
    us_aqi: float
    pm2_5: float | None = None
    pm10: float | None = None
    band: str | None = None
    source: str
    is_verified: bool


class WeatherResponse(BaseModel):
    location_label: str
    latitude: float
    longitude: float
    observed_at: str
    temperature_c: float
    condition: str
    rainfall_mm: float
    precip_probability_pct: float
    humidity_pct: float
    wind_kph: float
    source: str
    is_verified: bool
    # True when a cached (older) reading was served because the live
    # provider was unreachable. Data provenance stays in source/is_verified.
    degraded: bool = False
    # Optional enriched fields (None when the provider doesn't supply them).
    apparent_temperature_c: float | None = None
    wind_direction_deg: float | None = None
    wind_direction: str | None = None
    wind_gust_kph: float | None = None
    weather_code: int | None = None
    # Optional air-quality enrichment (None when unavailable/unfetched).
    air_quality: AirQualityOut | None = None


class ForecastDayResponse(BaseModel):
    date: str
    rainfall_mm: float
    temperature_c: float
    precipitation_probability_pct: float | None = None
    condition: str | None = None
    weather_code: int | None = None
    apparent_temperature_max_c: float | None = None
    wind_max_kph: float | None = None


class RiskResponse(BaseModel):
    """Single overall risk snapshot (legacy shape, kept for /weather/current)."""

    score: float
    level: str
    hazard_type: str | None
    explanation: str


class RiskItemResponse(BaseModel):
    """One detected risk from the risk engine."""

    category: str
    severity: str
    score: float
    title: str
    explanation: str
    guidance: list[str]
    affected_metric: str | None = None
    measured_value: float | None = None
    affected_day: str | None = None


class RiskAssessmentResponse(BaseModel):
    """Full role-aware risk assessment (GET /risk)."""

    latitude: float
    longitude: float
    role: str
    profile: str
    assessed_at: str
    weather: WeatherResponse
    condition: str
    overall_severity: str
    overall_score: float
    risks: list[RiskItemResponse]


class WeatherAndRiskResponse(BaseModel):
    weather: WeatherResponse
    risk: RiskResponse


class ForecastResponse(BaseModel):
    forecast: list[ForecastDayResponse]


class GeoPlaceOut(BaseModel):
    """One geocoding search result (GET /geo/search)."""

    name: str
    label: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None


class GeoSearchResponse(BaseModel):
    query: str
    results: list[GeoPlaceOut]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str
    language: str = "en"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    role: str = "customer"  # customer | farmer | traveler | disaster_management_officer
    scenario: str = "normal"  # demo-only; ignored once a real provider is wired up
    rag_enabled: bool = True  # allow clients to skip retrieval for quick status questions


class ChatResponse(BaseModel):
    reply: str
    data_used: dict
    language: str
    role: str
    fallback_used: bool = False  # True only when BOTH AI tiers failed and the deterministic reply was used
    provider: str | None = None  # which AI answered: ollama | solar | scope_guard | fallback
    sources: list[str] = []  # titles of retrieved knowledge-base documents
    weather: dict = {}  # weather context the answer is grounded in
    risks: list[dict] = []  # detected risks for the requested role


class SafeZone(BaseModel):
    name: str
    latitude: float
    longitude: float
    distance_km: float
    is_verified: bool


class RoutingResponse(BaseModel):
    """A road route from the OSRM proxy, in Leaflet-friendly form."""

    distance_km: float
    duration_min: int
    # [lat, lon] pairs along the road geometry.
    coordinates: list[list[float]]


class TravelTimesResponse(BaseModel):
    """Per-destination minutes from one origin (OSRM table proxy)."""

    mode: str
    # Aligned 1:1 with the requested destinations; None = unreachable.
    minutes: list[int | None]


class SosRequest(BaseModel):
    latitude: float
    longitude: float
    note: str | None = None
    user_id: str | None = None


class SosResponse(BaseModel):
    id: str
    logged: bool
    dispatched: bool
    message: str


class SafetyAlertOut(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    explanation: str
    recommended_action: str
    timestamp: str
    latitude: float
    longitude: float
    source: str
    is_official: bool
    valid_until: str | None = None


class ChecklistItemOut(BaseModel):
    text: str
    category: str


class LoginRequest(BaseModel):
    """Sign-in payload. `role` is the ONE-TIME role choice for the session."""

    username: str
    password: str
    # customer | farmer | traveler | disaster_management_officer
    # Optional: when omitted the account's own default role is used.
    role: str | None = None


class SessionUserOut(BaseModel):
    username: str
    display_name: str
    role: str
    is_admin: bool
    # True for the configured judge/hackathon account (computed from config,
    # never stored). The frontend uses it to auto-open the feature tour.
    is_judge: bool = False


class SessionResponse(BaseModel):
    """A dashboard session. `role` is locked for as long as it lives."""

    token: str
    role: str
    created_at: datetime
    expires_at: datetime
    user: SessionUserOut


class SafetyAssessmentOut(BaseModel):
    """WeatherGPT Safety Status for one location + role.

    `status` is WeatherGPT's own escalation label (normal/watch/warning/
    critical) — never an official government warning level.
    """

    latitude: float
    longitude: float
    role: str
    status: str
    generated_at: str
    weather_source: str
    weather_is_verified: bool
    observed_at: str
    condition: str
    temperature_c: float
    rainfall_mm: float
    wind_kph: float
    humidity_pct: float
    alerts: list[SafetyAlertOut]
    checklist: list[ChecklistItemOut]
    official_alerts: list[SafetyAlertOut]
    disclaimer: str
