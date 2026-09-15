"""
Risk profile configuration. The active profile (RISK_PROFILE env var,
default "default") supplies ALL thresholds, role priorities and guidance
templates — nothing is hard-coded in detectors or routes.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


class RainfallThresholds(BaseModel):
    moderate: float
    high: float
    extreme: float


class WindThresholds(BaseModel):
    moderate: float
    high: float
    extreme: float


class TemperatureThresholds(BaseModel):
    moderate: float
    high: float
    extreme: float


class HumidityThresholds(BaseModel):
    moderate: float
    high: float
    extreme: float


class FloodThresholds(BaseModel):
    moderate: float
    high: float
    extreme: float


class AqiThresholds(BaseModel):
    """US AQI bands for the AIR_QUALITY risk (display band is separate)."""

    moderate: float
    high: float
    extreme: float


class Thresholds(BaseModel):
    rainfall_mm_per_day: RainfallThresholds
    wind_kph: WindThresholds
    temperature_c: TemperatureThresholds
    apparent_temperature_c: TemperatureThresholds
    humidity_pct: HumidityThresholds
    flood_potential_mm_per_day: FloodThresholds
    us_aqi: AqiThresholds
    severe_weather_codes: list[int] = Field(default_factory=lambda: [95, 96, 99])
    windy_hours_min: int = 3


class RiskProfile(BaseModel):
    """Typed view of profiles/<name>.json."""

    profile: str
    description: str
    severities: tuple[str, ...]
    thresholds: Thresholds
    role_priorities: dict[str, list[str]]
    guidance_templates: dict[str, dict[str, str]]


@lru_cache(maxsize=None)
def get_risk_profile(name: str | None = None) -> RiskProfile:
    """Load and validate a risk profile by name (cached)."""
    profile_name = (name or get_configured_profile_name()).lower()
    path = _PROFILES_DIR / f"{profile_name}.json"
    if not path.is_file():
        available = sorted(p.stem for p in _PROFILES_DIR.glob("*.json"))
        raise ValueError(f"Unknown RISK_PROFILE '{profile_name}'. Available profiles: {', '.join(available) or 'none'}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = RiskProfile.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        log.error("risk_profile.load_failed profile=%s error=%s", profile_name, exc)
        raise ValueError(f"Risk profile '{profile_name}' is invalid: {exc}") from exc

    return profile


def get_configured_profile_name() -> str:
    """The profile selected by configuration (RISK_PROFILE, default 'default')."""
    from app.core.config import get_settings

    return get_settings().RISK_PROFILE.lower()
