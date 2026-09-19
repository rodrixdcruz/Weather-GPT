"""
Free cloud LLM presets for the hybrid provider's escalation tier.

The escalation tier used to be Solar Pro 4 (paid). It is now any
OpenAI-compatible chat-completions endpoint, and the presets below are the
providers that offer a **permanent free tier** — no credit card, no trial
expiry — so MausamBagha AI can answer broad-knowledge questions and cover for a
missing local model without a bill.

Adding a provider is one dict entry here; nothing in the routers or the
hybrid chain needs to know which one is live.

Facts in this table (base URLs, model ids, free-tier limits) were verified
against the providers' own docs in September 2026. They DO change over time:
`ESCALATION_MODEL` and `ESCALATION_BASE_URL` override anything here, and the
admin panel shows exactly which base URL/model is in use, so a stale entry is
visible rather than mysterious.

Keyless tiers (`requires_key=False`) exist because they make the whole
escalation path work with zero signup. They are slower and tightly
rate-limited, so they are the fallback default, not the recommendation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EscalationPreset:
    """One free (or legacy) escalation provider."""

    name: str
    label: str
    base_url: str
    model: str
    requires_key: bool
    signup_url: str | None
    limits: str
    notes: str = ""


# Ordered by how good a default they are (used for the "best available" hint
# in the admin panel). Groq first: free, no credit card, fastest inference,
# and by far the most generous request allowance.
PRESETS: dict[str, EscalationPreset] = {
    "groq": EscalationPreset(
        name="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",
        requires_key=True,
        signup_url="https://console.groq.com/keys",
        limits="30 req/min · 1,000 req/day",
        notes="Fastest free tier; the easiest single key to get. No credit card.",
    ),
    "gemini": EscalationPreset(
        name="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-flash",
        requires_key=True,
        signup_url="https://aistudio.google.com/apikey",
        limits="15 req/min · 1,500 req/day",
        notes="Most generous daily allowance. Free-tier prompts may be used to improve Google products.",
    ),
    "nvidia": EscalationPreset(
        name="nvidia",
        label="NVIDIA NIM",
        base_url="https://integrate.api.nvidia.com/v1",
        model="openai/gpt-oss-120b",
        requires_key=True,
        signup_url="https://build.nvidia.com",
        limits="40 req/min · 10,000 req/day",
        notes="Highest free request ceiling; needs a free NVIDIA developer account.",
    ),
    "openrouter": EscalationPreset(
        name="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        model="nvidia/nemotron-3-super-120b-a12b:free",
        requires_key=True,
        signup_url="https://openrouter.ai/keys",
        limits="20 req/min · 50 req/day",
        notes="One key reaches many models — pick any ':free' suffixed id via ESCALATION_MODEL.",
    ),
    "mistral": EscalationPreset(
        name="mistral",
        label="Mistral AI",
        base_url="https://api.mistral.ai/v1",
        model="mistral-small-latest",
        requires_key=True,
        signup_url="https://console.mistral.ai/api-keys",
        limits="~1 req/sec · monthly credit allowance",
        notes="Free mode is default for new accounts. Free-mode prompts may be used to train Mistral models.",
    ),
    "ovhcloud": EscalationPreset(
        name="ovhcloud",
        label="OVHcloud AI Endpoints",
        base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        model="Mistral-Nemo-Instruct-2407",
        requires_key=False,
        signup_url=None,
        limits="2 req/min per IP",
        notes="NO API KEY and no signup — this is what makes the tier work out of the box. EU-hosted open-weight models.",
    ),
    # Kept so an existing Solar Pro 4 key keeps working; no longer the default.
    "solar": EscalationPreset(
        name="solar",
        label="Solar Pro 4 (legacy, paid)",
        base_url="https://api.upstage.ai/v1/solar",
        model="solar-pro4",
        requires_key=True,
        signup_url="https://console.upstage.ai",
        limits="paid",
        notes="The previous escalation tier. Still supported; no longer the default.",
    ),
}

# Used when no provider is chosen and no key is present.
KEYLESS_FALLBACK = "ovhcloud"
# Used when a key is present but no provider is named.
KEYED_DEFAULT = "groq"
AUTO = "auto"

# The zero-configuration failover chain: OVHcloud first (keyless), then any
# free provider whose key happens to be configured. Meant to be short — each
# extra attempt adds latency to the unlucky request that needs it.
KEYLESS_CHAIN = [KEYLESS_FALLBACK]
KEYED_CHAIN = [KEYED_DEFAULT, KEYLESS_FALLBACK]


def preset_names() -> list[str]:
    return sorted(PRESETS)


def get_preset(name: str) -> EscalationPreset:
    """Look up a preset, with a helpful error naming the valid options."""
    key = (name or "").strip().lower()
    if key not in PRESETS:
        raise ValueError(
            f"Unknown escalation provider '{name}'. Valid options: {', '.join(preset_names())}."
        )
    return PRESETS[key]


def choose_preset_name(*, provider: str | None, has_api_key: bool) -> str:
    """Decide which preset to use.

    Explicit choice always wins. Otherwise prefer a real keyed free tier, and
    fall back to a keyless one so the escalation path is never dead on
    arrival just because nobody configured anything.
    """
    key = (provider or "").strip().lower()
    if key and key != AUTO:
        return key
    return KEYED_DEFAULT if has_api_key else KEYLESS_FALLBACK


def resolve_chain_names(
    *, provider: str | None, providers: str | None, has_api_key: bool
) -> list[str]:
    """Resolve the ordered failover chain for the escalation tier.

    ESCALATION_PROVIDERS (comma-separated) is the explicit chain and wins;
    "auto" entries inside it resolve like a bare ESCALATION_PROVIDER would
    (Groq when a key exists, else the keyless tier). With no chain and no
    explicit provider, key presence picks the default chain: KEYED_CHAIN
    (Groq → keyless) when a key is configured, otherwise the single keyless
    provider — zero-config behaves as before, and adding one free key
    switches failover on without touching any other setting.

    Names are validated (unknown ones raise with the valid options) and
    de-duplicated preserving order.
    """
    raw = [p.strip().lower() for p in (providers or "").split(",") if p.strip()]
    if not raw:
        if (provider or "").strip().lower() in ("", AUTO):
            # Fully automatic mode: a configured free key upgrades the tier
            # to the real failover chain (keyed first, keyless behind it);
            # with no key there is nothing to fail over TO, so it stays a
            # single keyless provider.
            return list(KEYED_CHAIN) if has_api_key else list(KEYLESS_CHAIN)
        return [choose_preset_name(provider=provider, has_api_key=has_api_key)]

    chain: list[str] = []
    for name in raw:
        resolved = choose_preset_name(provider=name, has_api_key=has_api_key) if name == AUTO else name
        get_preset(resolved)  # validates; raises with the valid options
        if resolved not in chain:
            chain.append(resolved)
    return chain
