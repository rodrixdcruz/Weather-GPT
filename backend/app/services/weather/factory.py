from app.core.config import get_settings
from app.services.weather.air_quality import OpenMeteoAirQualityProvider, attach_air_quality
from app.services.weather.base import WeatherProvider, WeatherReading
from app.services.weather.mock_provider import MockWeatherProvider


def get_weather_provider(scenario: str = "normal") -> WeatherProvider:
    settings = get_settings()
    provider = settings.WEATHER_PROVIDER.lower()

    if provider == "mock":
        # The mock ships deterministic per-scenario AQI fixtures, so the
        # demo scenarios (incl. smog) work offline — no AQI HTTP enrichment.
        return MockWeatherProvider(scenario=scenario)
    if provider == "open_meteo":
        from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider

        return _with_air_quality_and_resilience(OpenMeteoWeatherProvider())
    if provider == "met_norway":
        from app.services.weather.met_norway_provider import MetNorwayWeatherProvider

        return _with_air_quality_and_resilience(MetNorwayWeatherProvider())

    raise ValueError(f"Unknown WEATHER_PROVIDER '{provider}'. Add a provider in services/weather/.")


def _with_air_quality_and_resilience(provider_impl: WeatherProvider) -> WeatherProvider:
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

    return ResilientWeatherProvider(provider_impl)
