"""
Safety checklists: deterministic, general, safety-oriented guidance items
selected by active risk category and role. Items are intentionally
non-specific (no crop/medical/structural claims) and phrased as ordinary
precautions. Only categories with an active risk contribute items.
"""
from app.services.risk.models import RiskCategory, Severity, RiskItem

# Minimum severity for a category's checklist to activate.
_ACTIVATION = {
    RiskCategory.RAINFALL: Severity.MODERATE,
    RiskCategory.FLOOD_POTENTIAL: Severity.MODERATE,
    RiskCategory.HIGH_TEMPERATURE: Severity.MODERATE,
    RiskCategory.HEAT_STRESS: Severity.MODERATE,
    RiskCategory.STRONG_WIND: Severity.MODERATE,
    RiskCategory.SEVERE_WEATHER: Severity.MODERATE,
    RiskCategory.POOR_TRAVEL_CONDITIONS: Severity.MODERATE,
    RiskCategory.ACTIVITY_DISRUPTION: Severity.MODERATE,
    RiskCategory.AIR_QUALITY: Severity.MODERATE,
}

# text, category. Ordered most-broad first; capped per category below.
_ITEMS = {
    RiskCategory.RAINFALL: [
        "Avoid unnecessary travel during the heaviest rain periods",
        "Protect important documents and electronics from water",
        "Keep communication devices charged in case of power cuts",
    ],
    RiskCategory.FLOOD_POTENTIAL: [
        "Never walk or drive through water of unknown depth",
        "Move vehicles and valuables above expected water levels",
        "Follow official flood advisories from local authorities",
    ],
    RiskCategory.HIGH_TEMPERATURE: [
        "Reduce strenuous outdoor activity in the hottest hours",
        "Drink water regularly, even without feeling thirsty",
        "Check on elderly neighbours, children and outdoor workers",
    ],
    RiskCategory.HEAT_STRESS: [
        "Rest in shade or cool spaces and pace physical work",
        "Use light clothing, hats and sunscreen outdoors",
        "Seek medical help if heat exhaustion symptoms are severe",
    ],
    RiskCategory.STRONG_WIND: [
        "Secure or bring indoors loose outdoor objects",
        "Keep clear of trees, hoardings and power lines in gusts",
        "Take extra care driving high-sided vehicles on exposed roads",
    ],
    RiskCategory.SEVERE_WEATHER: [
        "Stay indoors away from windows during the storm",
        "Unplug sensitive electronics until the storm passes",
        "Monitor official warnings and follow authority instructions",
    ],
    RiskCategory.POOR_TRAVEL_CONDITIONS: [
        "Allow extra journey time and reduce driving speed",
        "Use headlights in rain and watch for waterlogged roads",
        "Consider postponing non-essential trips",
    ],
    RiskCategory.ACTIVITY_DISRUPTION: [
        "Have an indoor backup plan for outdoor activities",
        "Communicate schedule changes to participants early",
    ],
    RiskCategory.AIR_QUALITY: [
        "Limit strenuous outdoor activity while air quality is poor",
        "Keep windows closed during the worst pollution hours",
        "People with respiratory conditions should carry their medication",
    ],
}

# Items added regardless of active risks (always-relevant preparedness).
_ALWAYS = [
    "Keep an emergency kit: water, food, torch, medicines, documents",
    "Save local emergency numbers (India national helpline: 112)",
]

_ROLE_CAPS = {
    "customer": 4,
    "farmer": 5,
    "traveler": 4,
    "disaster_management_officer": 6,
}


def build_checklist(risks: list[RiskItem], role: str) -> list[tuple[str, str]]:
    """Deterministic checklist for the active risks and role.

    Returns (text, category) tuples. Categories whose risk is below the
    activation severity contribute nothing; the role only changes how many
    items are shown, never the safety content itself.
    """
    items: list[tuple[str, str]] = []
    cap = _ROLE_CAPS.get(role, 4)

    # Most severe risks first for ordering.
    for risk in sorted(risks, key=lambda r: -r.severity.rank):
        minimum = _ACTIVATION.get(risk.category)
        if minimum is None or risk.severity.rank < minimum.rank:
            continue
        category_items = _ITEMS.get(risk.category, [])
        if risk.severity.rank >= Severity.HIGH.rank:
            # Elevated risks surface all their items first.
            items.extend((text, risk.category.value) for text in category_items)
        else:
            items.extend((text, risk.category.value) for text in category_items[:2])

    result = items[:cap]
    result.extend((always_text, "preparedness") for always_text in _ALWAYS)
    return result
