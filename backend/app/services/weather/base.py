"""
Weather data provider abstraction. Swappable the same way as the AI
provider — set WEATHER_PROVIDER in env. Every reading returned MUST
carry `source` and `is_verified` so the frontend can label it correctly;
never fabricate a "verified" reading from a model estimate.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.weather.air_quality import AirQuality

# Compass-point names for the 16 principal directions, indexed by the
# bearing bucket floor(bearing / 22.5). Used to turn degrees of wind
# direction into human-readable text for the UI.
COMPASS_POINTS: tuple[str, ...] = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)


def wind_direction_to_compass(degrees: float) -> str:
    """Convert a wind bearing in degrees to a 16-point compass label."""
    normalized = degrees % 360
    index = int((normalized + 11.25) // 22.5) % 16
    return COMPASS_POINTS[index]


@dataclass
class WeatherReading:
    location_label: str
    latitude: float
    longitude: float
    observed_at: str  # ISO 8601
    temperature_c: float
    condition: str
    rainfall_mm: float
    precip_probability_pct: float
    humidity_pct: float
    wind_kph: float
    source: str
    is_verified: bool
    # Optional enriched fields. Providers that don't have a field set it
    # to None; the risk engine treats None as "no data" and skips that
    # detector rather than guessing.
    apparent_temperature_c: float | None = None
    wind_direction_deg: float | None = None
    wind_direction: str | None = None
    wind_gust_kph: float | None = None
    weather_code: int | None = None
    # Optional air-quality enrichment (None = not fetched / not available).
    # Attached only by enrich_with_air_quality(); never fabricated.
    air_quality: "AirQuality | None" = None


@dataclass
class ForecastDay:
    date: str
    rainfall_mm: float
    temperature_c: float
    # Optional enriched fields (None when the provider lacks them).
    precipitation_probability_pct: float | None = None
    condition: str | None = None
    weather_code: int | None = None
    apparent_temperature_max_c: float | None = None
    wind_max_kph: float | None = None


class WeatherProviderError(Exception):
    """Raised when a weather provider cannot return usable data.

    Carries a machine-readable `kind` (upstream_unavailable | upstream_error |
    malformed_response) and a safe, user-facing `detail`. Never include
    upstream internals or secrets in `detail` — it goes straight into the
    HTTP response.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class WeatherProvider(ABC):
    @abstractmethod
    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        raise NotImplementedError

    @abstractmethod
    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        raise NotImplementedError
