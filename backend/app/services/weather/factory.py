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

        provider_impl = OpenMeteoWeatherProvider()
        if settings.AIR_QUALITY_ENABLED:
            # Key-less Open-Meteo Air Quality API enrichment. Wrapped so any
            # AQI failure degrades to "no AQI" instead of breaking weather.
            aqi_provider = OpenMeteoAirQualityProvider()
            original_get_current = provider_impl.get_current

            async def get_current_with_aqi(latitude: float, longitude: float) -> WeatherReading:
                reading = await original_get_current(latitude, longitude)
                return await attach_air_quality(reading, aqi_provider)

            provider_impl.get_current = get_current_with_aqi  # type: ignore[method-assign]
        return provider_impl

    raise ValueError(f"Unknown WEATHER_PROVIDER '{provider}'. Add a provider in services/weather/.")
