"""
Solar Pro 4 (Upstage API) — the LEGACY escalation tier.

Solar used to be the only escalation provider. It is now just one entry in
`presets.py` alongside the free ones (Groq, Gemini, NVIDIA NIM, OpenRouter,
Mistral, keyless OVHcloud), and it is no longer the default because it is the
only option that costs money.

This class is kept so existing deployments keep working unchanged: with
`ESCALATION_PROVIDER=solar` (or `AI_PROVIDER` untouched and SOLAR_API_KEY
set) it behaves exactly as before, reading SOLAR_* settings and answering as
provider "solar".

All the work lives in CloudChatProvider — this is only the configuration
wrapper that binds the Solar preset to the SOLAR_* env vars.
"""
from app.core.config import get_settings
from app.services.ai.cloud_provider import CloudChatProvider
from app.services.ai.presets import get_preset


class SolarProvider(CloudChatProvider):
    """Talks to the Upstage Solar Pro 4 chat-completions endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        super().__init__(
            preset=get_preset("solar"),
            provider_name="solar",
            # Solar keeps its own env vars; an explicit argument always wins,
            # including an explicit None (used by tests to force "no key").
            api_key=settings.SOLAR_API_KEY if api_key is None else api_key,
            base_url=settings.SOLAR_API_BASE_URL if base_url is None else base_url,
            model=model or settings.SOLAR_MODEL or "solar-pro4",
            timeout=settings.SOLAR_TIMEOUT_SECONDS if timeout is None else timeout,
        )
