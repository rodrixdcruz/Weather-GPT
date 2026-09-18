from app.core.config import get_settings
from app.services.weather.air_quality import OpenMeteoAirQualityProvider, attach_air_quality
from app.services.weather.base import WeatherProvider, WeatherReading
from app.services.weather.mock_provider import MockWeatherProvider
from app.services.weather.scenario_overlay import SCENARIO_NAMES, bend_forecast, bend_reading


def get_weather_provider(scenario: str = "normal", judge: bool = False) -> WeatherProvider:
    """Build the provider stack for one request.

    `scenario` is a JUDGE-ONLY demo knob: callers pass `judge=True` only when
    the request's session belongs to the judge account (see
    resolve_demo_scenario), so public traffic can never trigger simulated
    weather. With a live provider, the scenario "bends" real readings
    toward the scenario profile (overlay below); with the mock provider the
    fixtures already embody the scenarios, and the scenario flag is just
    passed through for the fixtures to select.
    """
    settings = get_settings()
    provider = settings.WEATHER_PROVIDER.lower()

    if provider == "mock":
        # The mock ships deterministic per-scenario AQI fixtures, so the
        # demo scenarios (incl. smog) work offline — no AQI HTTP enrichment.
        return MockWeatherProvider(scenario=scenario if judge else "normal")
    if provider == "open_meteo":
        from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider

        return _with_air_quality_and_resilience(OpenMeteoWeatherProvider(), scenario=scenario if judge else "normal")
    if provider == "met_norway":
        from app.services.weather.met_norway_provider import MetNorwayWeatherProvider

        return _with_air_quality_and_resilience(MetNorwayWeatherProvider(), scenario=scenario if judge else "normal")

    raise ValueError(f"Unknown WEATHER_PROVIDER '{provider}'. Add a provider in services/weather/.")


def resolve_demo_scenario(scenario: str | None, session) -> str:
    """Validate the scenario request against the caller's session.

    Returns the effective scenario name. ANY session may ask for "normal"
    (that is the live-data default). A named scenario is honoured ONLY for
    the judge account — everyone else gets "normal", silently. Raises 403
    for an unknown scenario name even for judges (bad input ≠ simulation).
    """
    from fastapi import HTTPException

    requested = (scenario or "normal").strip().lower() or "normal"
    if requested == "normal":
        return "normal"
    if requested not in SCENARIO_NAMES:
        raise HTTPException(status_code=403, detail=f"Unknown demo scenario '{requested}'.")

    from app.services.auth.service import is_judge_account

    if session is not None and is_judge_account(session.account):
        return requested
    # Deliberately silent: a non-judge asking for a scenario gets live data
    # rather than an error, so public traffic is never disrupted.
    return "normal"


def _with_air_quality_and_resilience(provider_impl: WeatherProvider, scenario: str = "normal") -> WeatherProvider:
    """Shared wiring for every live provider: optional key-less AQI
    enrichment (failure-tolerant, never breaks weather) and the resilience
    layer — shared egress IPs on cloud platforms hit key-less API limits
    (observed: Open-Meteo 429s Render's egress pool), so upstream trouble
    degrades to clearly-labeled cached or fixture data instead of a 502."""
    settings = get_settings()
    if settings.AIR_QUALITY_ENABLED:
        aqi_provider = OpenMeteoAirQualityProvider()
        original_get_current = provider_impl.get_current

        async def get_current_with_aqi(latitude: float, longitude: float) -> WeatherReading:
            reading = await original_get_current(latitude, longitude)
            return await attach_air_quality(reading, aqi_provider)

        provider_impl.get_current = get_current_with_aqi  # type: ignore[method-assign]

    from app.services.weather.resilient import ResilientWeatherProvider
    from app.services.weather.scenario_overlay import ScenarioOverlayProvider

    resilient = ResilientWeatherProvider(provider_impl)
    if scenario != "normal":
        return ScenarioOverlayProvider(resilient, scenario)
    return resilient
