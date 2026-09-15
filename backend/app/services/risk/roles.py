"""
Role overlay. Roles change HOW risks are presented — ordering,
explanation emphasis and guidance — but NEVER the underlying weather
measurements or the raw detector results.
"""
from app.services.risk.models import RiskItem
from app.services.risk.profile import RiskProfile

CUSTOMER = "customer"
FARMER = "farmer"
TRAVELER = "traveler"
DISASTER_MANAGEMENT_OFFICER = "disaster_management_officer"

KNOWN_ROLES = (CUSTOMER, FARMER, TRAVELER, DISASTER_MANAGEMENT_OFFICER)
DEFAULT_ROLE = CUSTOMER


def normalize_role(role: str | None) -> str:
    """Accept case-insensitive / hyphenated variants; fall back to default."""
    if not role:
        return DEFAULT_ROLE
    candidate = role.strip().lower().replace("-", "_").replace(" ", "_")
    return candidate if candidate in KNOWN_ROLES else DEFAULT_ROLE


def sort_risks_for_role(risks: list[RiskItem], profile: RiskProfile, role: str) -> list[RiskItem]:
    """Order risks by the role's priority list, then severity, then score."""
    priorities = profile.role_priorities.get(role, profile.role_priorities[DEFAULT_ROLE])
    priority_index = {category: index for index, category in enumerate(priorities)}
    # Unknown categories sort last; severity then score break ties.
    return sorted(
        risks,
        key=lambda r: (
            priority_index.get(r.category.value, len(priorities)),
            -r.severity.rank,
            -r.score,
        ),
    )
