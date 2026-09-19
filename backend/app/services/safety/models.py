"""
Safety-layer models.

Key contract: everything here is MausamBagha AI-generated interpretation of
weather data, explicitly NOT an official government alert. Models carry
`source` fields so the UI can always distinguish the two. Official alerts
can only enter the system through a SafetyAlertProvider (see providers.py)
— and no such provider ships by default, so none are fabricated.
"""
from dataclasses import dataclass, field
from enum import Enum

# MausamBagha AI's own escalation ladder, derived deterministically from risk
# severity. Deliberately labeled "MausamBagha AI Safety Status" in the UI —
# these are NOT official government warning levels.
ESCALATION_ORDER = ("normal", "watch", "warning", "critical")


class SafetyStatus(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"

    @classmethod
    def from_severity(cls, severity_value: str) -> "SafetyStatus":
        mapping = {"low": "normal", "moderate": "watch", "high": "warning", "extreme": "critical"}
        return cls(mapping.get(severity_value, "normal"))

    @property
    def rank(self) -> int:
        return ESCALATION_ORDER.index(self.value)


@dataclass
class SafetyAlert:
    """One actionable safety alert derived from the risk engine (or an
    official provider, when one is configured)."""

    id: str  # stable/deterministic id, used for de-duplication
    category: str
    severity: str  # low | moderate | high | extreme
    title: str
    explanation: str
    recommended_action: str
    timestamp: str  # ISO 8601
    latitude: float
    longitude: float
    source: str  # e.g. "weathergpt_risk_engine" — never claim official origin
    is_official: bool = False
    valid_until: str | None = None  # expiry/validity where applicable


@dataclass
class ChecklistItem:
    text: str
    category: str  # risk category the item mitigates


@dataclass
class SafetyAssessment:
    """Everything the Safety dashboard needs, for one location + role."""

    latitude: float
    longitude: float
    role: str
    status: str  # SafetyStatus value
    generated_at: str
    weather_source: str
    weather_is_verified: bool
    observed_at: str
    condition: str
    temperature_c: float
    rainfall_mm: float
    wind_kph: float
    humidity_pct: float
    alerts: list[SafetyAlert] = field(default_factory=list)
    checklist: list[ChecklistItem] = field(default_factory=list)
    official_alerts: list[SafetyAlert] = field(default_factory=list)
    disclaimer: str = (
        "MausamBagha AI Safety Status is an automated interpretation of weather data. "
        "It is NOT an official government warning. For authoritative forecasts and "
        "alerts follow your national meteorological service and local authorities."
    )

    @property
    def overall_alert_count(self) -> int:
        return len(self.alerts)
