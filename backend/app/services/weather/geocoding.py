"""
Location search backed by Open-Meteo's key-less Geocoding API
(https://open-meteo.com/en/docs/geocoding-api, GeoNames data).

Same conventions as the weather/air-quality services:
- Injectable httpx transport so tests never hit the live API.
- Typed errors with pre-sanitized, user-safe details.
- Never fabricates results: an unknown place name is an empty result,
  not an error; only transport/HTTP/parse failures are errors.
"""
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 8.0
_DEFAULT_BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass
class GeoPlace:
    """One search result, ready for the location inputs the UI already has."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None  # state/region, when the provider has it
    timezone: str | None = None

    @property
    def label(self) -> str:
        """Human-readable label: "Mumbai, Maharashtra, India" style."""
        parts = [self.name, self.admin1, self.country]
        return ", ".join(p for p in parts if p)


class GeoCodingError(Exception):
    """Raised when the geocoding service cannot be reached or parsed.

    Carries a machine-readable `kind` and a pre-sanitized `detail`,
    matching WeatherProviderError / AirQualityProviderError.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class OpenMeteoGeoCoder:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    async def search(self, query: str, count: int = 5) -> list[GeoPlace]:
        query = (query or "").strip()
        if not query:
            return []  # empty input -> empty result, not an error

        params = {"name": query, "count": count, "language": "en", "format": "json"}
        payload = await self._fetch(params)

        results = payload.get("results")
        if results is None:
            return []  # Open-Meteo omits `results` when nothing matches
        if not isinstance(results, list):
            raise GeoCodingError("malformed_response", "The location service returned an unreadable response.")

        places: list[GeoPlace] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            latitude = _optional_number(item, "latitude")
            longitude = _optional_number(item, "longitude")
            if not name or latitude is None or longitude is None:
                continue  # skip malformed entries rather than failing the batch
            places.append(
                GeoPlace(
                    name=str(name),
                    latitude=latitude,
                    longitude=longitude,
                    country=_optional_str(item, "country"),
                    admin1=_optional_str(item, "admin1"),
                    timezone=_optional_str(item, "timezone"),
                )
            )
        return places

    async def _fetch(self, params: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = await client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("geocoding.timeout url=%s", self._base_url)
            raise GeoCodingError("upstream_unavailable", "The location service did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("geocoding.connection_error url=%s error=%s", self._base_url, type(exc).__name__)
            raise GeoCodingError("upstream_unavailable", "Could not reach the location service.") from exc

        if response.status_code >= 400:
            log.warning("geocoding.http_error status=%s", response.status_code)
            raise GeoCodingError("upstream_error", f"The location service returned an error (HTTP {response.status_code}).")

        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("geocoding.malformed_json")
            raise GeoCodingError("malformed_response", "The location service returned an unreadable response.") from exc

        if not isinstance(payload, dict):
            raise GeoCodingError("malformed_response", "The location service returned an unreadable response.")
        return payload


def _optional_number(item: dict, key: str) -> float | None:
    value = item.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(item: dict, key: str) -> str | None:
    value = item.get(key)
    return str(value) if value is not None else None
