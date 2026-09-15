"""
Normalized weather -> Risk Detectors -> Risk Category + Severity + Score
-> Role Overlay -> Risk Assessment -> API -> React UI

Risk models live here, independent of any weather provider. Detectors
consume ONLY the canonical WeatherReading/ForecastDay models, so the risk
engine stays provider-agnostic and testable in isolation.
"""
from dataclasses import dataclass, field
from enum import Enum

SEVERITY_LEVELS = ("low", "moderate", "high", "extreme")


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"

    @classmethod
    def from_rank(cls, rank: int) -> "Severity":
        """Map a 0-3 rank (index into SEVERITY_LEVELS) to a Severity."""
        rank = max(0, min(len(SEVERITY_LEVELS) - 1, rank))
        return cls(SEVERITY_LEVELS[rank])

    @property
    def rank(self) -> int:
        return SEVERITY_LEVELS.index(self.value)


class RiskCategory(str, Enum):
    RAINFALL = "rainfall"
    HIGH_TEMPERATURE = "high_temperature"
    HEAT_STRESS = "heat_stress"
    STRONG_WIND = "strong_wind"
    SEVERE_WEATHER = "severe_weather"
    FLOOD_POTENTIAL = "flood_potential"
    POOR_TRAVEL_CONDITIONS = "poor_travel_conditions"
    ACTIVITY_DISRUPTION = "activity_disruption"
    # Present only when real air-quality data exists (Open-Meteo AQI
    # enrichment or the mock fixture). The engine treats a reading without
    # air quality as "no data" — the detector simply stays silent.
    AIR_QUALITY = "air_quality"


@dataclass
class RiskItem:
    """One detected risk from a single detector."""

    category: RiskCategory
    severity: Severity
    score: float  # 0-100, understandable magnitude for UI bars/gauges
    title: str
    explanation: str
    guidance: list[str] = field(default_factory=list)
    affected_metric: str | None = None
    measured_value: float | None = None
    affected_day: str | None = None  # date string for forecast-driven risks
    source: str = "weathergpt_risk_engine"


@dataclass
class RiskAssessment:
    """The full result of running all detectors over a weather snapshot."""

    latitude: float
    longitude: float
    role: str
    profile: str
    assessed_at: str  # ISO 8601
    weather_source: str
    weather_is_verified: bool
    observed_at: str
    condition: str
    risks: list[RiskItem] = field(default_factory=list)

    @property
    def overall_severity(self) -> Severity:
        return max((r.severity for r in self.risks), key=lambda s: s.rank, default=Severity.LOW)

    @property
    def overall_score(self) -> float:
        """Overall score: the highest risk's score, kept interpretable."""
        if not self.risks:
            return 0.0
        return round(max(r.score for r in self.risks), 1)
