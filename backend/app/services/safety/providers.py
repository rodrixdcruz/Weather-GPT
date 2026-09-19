"""
Official-alert provider abstraction.

MausamBagha AI NEVER fabricates government alerts. Official warnings can only
enter through a SafetyAlertProvider implementation backed by a real,
authoritative feed. The default `null` provider returns an empty list and
the UI clearly separates "MausamBagha AI-generated risk" from "official
alerts" (of which there are none until a real provider is configured via
SAFETY_ALERT_PROVIDER).
"""
import logging
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.services.safety.models import SafetyAlert

log = logging.getLogger(__name__)


class SafetyAlertProvider(ABC):
    """Fetch OFFICIAL safety alerts for a location, if any provider exists."""

    name: str = "abstract"

    @abstractmethod
    async def get_alerts(self, latitude: float, longitude: float) -> list[SafetyAlert]:
        raise NotImplementedError


class NullSafetyAlertProvider(SafetyAlertProvider):
    """No official feed configured — always returns no official alerts.

    This is the honest default. The safety dashboard still works: it shows
    MausamBagha AI-derived status with the official-source disclaimer.
    """

    name = "null"

    async def get_alerts(self, latitude: float, longitude: float) -> list[SafetyAlert]:
        return []


_provider: SafetyAlertProvider | None = None


def get_safety_alert_provider() -> SafetyAlertProvider:
    """Return the provider selected by SAFETY_ALERT_PROVIDER (default null)."""
    global _provider
    if _provider is None:
        selected = get_settings().SAFETY_ALERT_PROVIDER.lower()
        if selected == "null":
            _provider = NullSafetyAlertProvider()
        else:
            log.warning("safety.unknown_alert_provider provider=%s falling_back_to_null", selected)
            _provider = NullSafetyAlertProvider()
    return _provider


def set_safety_alert_provider(provider: SafetyAlertProvider) -> None:
    """Install a provider directly (used by tests and future integrations)."""
    global _provider
    _provider = provider


def reset_safety_alert_provider() -> None:
    """Forget the cached provider (test isolation)."""
    global _provider
    _provider = None
