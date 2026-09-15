"""
Role-aware guidance resolution. Reads from the active profile's
`guidance_templates` — detectors never hard-code user-facing copy for
roles, they just ask for it here.
"""
from app.services.risk.models import RiskCategory
from app.services.risk.profile import RiskProfile

# Fallback used when a profile has no template for a category+role pair;
# keeps guidance present but generic rather than crashing.
_GENERIC_GUIDANCE = "Monitor local weather updates and take sensible precautions for the conditions described."


def guidance_for(
    profile: RiskProfile,
    category: RiskCategory,
    role: str,
    fallback: str | None = None,
) -> str:
    """Resolve guidance text for a risk category and role.

    Falls back in order: category+role template -> category+customer
    template -> explicit fallback -> generic line.
    """
    templates = profile.guidance_templates.get(category.value, {})
    role_text = templates.get(role)
    if role_text:
        return role_text
    customer_text = templates.get("customer")
    if customer_text:
        return customer_text
    return fallback or _GENERIC_GUIDANCE
