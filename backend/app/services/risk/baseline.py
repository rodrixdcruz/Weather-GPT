"""
Baseline ("anomaly-lite") abstraction.

WeatherGPT deliberately does NOT pretend to have historical climate
anomaly data. Detectors compare measurements against the configured
meteorological baseline thresholds in the risk profile. This module
exists so a future historical/climatological provider (e.g. 30-year
normal rainfall for the coordinates) can be plugged in without touching
detector code: they only ever call `BaselineProvider`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.risk.profile import RiskProfile


@dataclass(frozen=True)
class BaselineContext:
    """What a detector needs to interpret one measurement in context."""

    baseline_source: str  # e.g. "profile_default", "climatology_1991_2020"
    thresholds: dict[str, float]  # e.g. {"moderate": 35.6, "high": 64.5, "extreme": 115.6}


class BaselineProvider(ABC):
    """Resolves which thresholds apply for a measurement at a location."""

    @abstractmethod
    def thresholds_for(self, metric: str, latitude: float, longitude: float) -> BaselineContext:
        raise NotImplementedError


class NullBaselineProvider(BaselineProvider):
    """Uses only the active risk profile's baseline thresholds.

    This is the honest default: thresholds come from the configured
    profile, and `baseline_source` says so. No anomaly-vs-history claims
    are made anywhere downstream.
    """

    def __init__(self, profile: RiskProfile) -> None:
        self._profile = profile

    def thresholds_for(self, metric: str, latitude: float, longitude: float) -> BaselineContext:
        thresholds = getattr(self._profile.thresholds, metric, None)
        if thresholds is None:
            raise KeyError(f"No baseline thresholds configured for metric '{metric}'")
        # Pydantic models expose threshold groups as attributes with
        # moderate/high/extreme fields.
        return BaselineContext(
            baseline_source="profile_default",
            thresholds={"moderate": thresholds.moderate, "high": thresholds.high, "extreme": thresholds.extreme},
        )


# Module-level default so detectors can be constructed with zero wiring;
# tests can inject anything BaselineProvider-compatible.
_default_provider: BaselineProvider | None = None


def get_baseline_provider(profile: RiskProfile) -> BaselineProvider:
    """Return the process-wide baseline provider, creating it if needed."""
    global _default_provider
    if _default_provider is None:
        _default_provider = NullBaselineProvider(profile)
    return _default_provider


def reset_baseline_provider() -> None:
    """Forget the cached provider (used by tests to isolate state)."""
    global _default_provider
    _default_provider = None


def set_baseline_provider(provider: BaselineProvider) -> None:
    """Install a custom baseline provider (used by tests / future features)."""
    global _default_provider
    _default_provider = provider
