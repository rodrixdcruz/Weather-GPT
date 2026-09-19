"""
Server-side proxy for road routing, backed by FOSSGIS's public OSRM instance
(the same servers that power directions on openstreetmap.org — free, key-less).

Why a backend proxy instead of browser → OSRM: browsers hit FOSSGIS directly,
uncoordinated — every visitor, every re-render, every HMR churn spends the
per-IP fair-use budget separately, and nothing is shared between them.
Routing through this backend:

- coalesces ALL visitors' requests for the same ~110 m cell + travel mode
  into ONE upstream call per TTL window (process-wide cache below),
- applies one uniform retry/timeout policy server-side (a browser retry
  storm just burns the budget faster),
- presents FOSSGIS a single identifiable, well-behaved client (User-Agent
  below) instead of uncontrolled public traffic.

Design mirrors the weather resilience layer (services/weather/resilient.py):
cache first, one retry for transient throttles, typed errors — a route is
never fabricated. Caches live at module level because a service instance is
created per request; the cache must outlive individual instances.
"""
import asyncio
import random
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class RoutingError(Exception):
    """Typed routing failure. `kind` maps to a clean HTTP status in the router."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


# --- process-wide caches ----------------------------------------------------
ROUTE_FRESH_TTL_SECONDS = 600.0  # road geometry is stable; 10 min is generous
TABLE_FRESH_TTL_SECONDS = 300.0  # travel-time badges track the moving origin
FAILURE_TTL_SECONDS = 30.0       # an upstream hiccup must not outlive itself
MAX_CACHE_ENTRIES = 2048         # bound memory; far above realistic usage

_route_cache: dict[tuple, tuple[Any, float]] = {}
_table_cache: dict[tuple, tuple[Any, float]] = {}


def reset_routing_caches() -> None:
    """Forget every cached route/table (test isolation)."""
    _route_cache.clear()
    _table_cache.clear()


# FOSSGIS's multi-server setup: car and foot networks live on separate hosts.
_MODES = {
    "driving": {"server": "routed-car", "profile": "driving"},
    "walking": {"server": "routed-foot", "profile": "foot"},
}

# Generous: FOSSGIS's foot-profile table can take >8s on a cold cache, and a
# timeout here has no retry (only 429s do) — one patient attempt beats a fast
# failure. Still well inside the frontend's 20s client ceiling.
_DEFAULT_TIMEOUT_SECONDS = 15.0
# FOSSGIS fair-use asks for an identifying User-Agent. No secrets here —
# it is the public repository URL.
_USER_AGENT = "MausamBagha AI/0.1 (https://github.com/rodrixdcruz/Weather-GPT)"


def _round(v: float) -> float:
    # ~110 m cells: identical across re-renders/location jitter, distinct for
    # genuinely different spots. Same cell size the frontend used before the
    # proxy existed.
    return round(float(v), 3)


def _evict_if_needed(cache: dict) -> None:
    """Keep the cache bounded: drop expired entries, then oldest-inserted."""
    if len(cache) < MAX_CACHE_ENTRIES:
        return
    now = time.monotonic()
    for key in [k for k, (_, at) in cache.items() if now - at > FAILURE_TTL_SECONDS]:
        del cache[key]
    while len(cache) >= MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)))


class OsrmRoutingService:
    def __init__(
        self,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # ROUTING_OSRM_BASE_URL lets a deployment point at a self-hosted OSRM
        # instead of the shared FOSSGIS instance.
        self._base_url = (get_settings().ROUTING_OSRM_BASE_URL or "https://routing.openstreetmap.de").rstrip("/")
        self._timeout_seconds = timeout_seconds
        # Injectable transport for tests (httpx.MockTransport); None = real network.
        self._transport = transport

    # --- public API ---------------------------------------------------------

    async def get_route(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        mode: str = "driving",
    ) -> dict[str, Any]:
        """Road route between two points.

        Returns `{distance_km, duration_min, coordinates}` with coordinates as
        [lat, lon] pairs (Leaflet order). Raises RoutingError('no_route') when
        the network exists but that mode cannot traverse it, and
        RoutingError('route_unavailable'/'upstream_*') for service problems.
        """
        cfg = _MODES.get(mode)
        if cfg is None:
            raise RoutingError("invalid_mode", f"Unsupported travel mode: {mode}")

        key = ("route", cfg["server"], _round(from_lat), _round(from_lon), _round(to_lat), _round(to_lon))
        hit = _route_cache.get(key)
        if hit is not None:
            value, at = hit
            if time.monotonic() - at < ROUTE_FRESH_TTL_SECONDS:
                return value
            _route_cache.pop(key, None)

        path = f"{from_lon:.6f},{from_lat:.6f};{to_lon:.6f},{to_lat:.6f}"
        url = (
            f"{self._base_url}/{cfg['server']}/route/v1/{cfg['profile']}/{path}"
            f"?overview=full&geometries=geojson&alternatives=false&steps=false"
        )
        payload = await self._fetch_json(url, error_kind="route_unavailable")
        route = (payload.get("routes") or [None])[0] if isinstance(payload, dict) else None
        geometry = route.get("geometry") if isinstance(route, dict) else None
        coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if payload.get("code") != "Ok" or not isinstance(coords, list) or not coords:
            raise RoutingError("no_route", "No road route exists between these points for this travel mode.")

        value = {
            "distance_km": round(float(route["distance"]) / 1000.0, 2),
            "duration_min": max(1, round(float(route["duration"]) / 60.0)),
            # GeoJSON is [lon, lat]; the map consumes [lat, lon].
            "coordinates": [[c[1], c[0]] for c in coords],
        }
        _evict_if_needed(_route_cache)
        _route_cache[key] = (value, time.monotonic())
        # No coordinates in logs — cache keys already avoid PII in messages.
        log.info(
            "routing.route mode=%s duration_min=%s distance_km=%s",
            mode, value["duration_min"], value["distance_km"],
        )
        return value

    async def get_travel_times(
        self,
        from_lat: float,
        from_lon: float,
        destinations: list[tuple[float, float]],
        mode: str = "driving",
    ) -> list[int | None]:
        """Minutes from one origin to each destination, in a single OSRM table
        request. Unreachable destinations come back as None (OSRM itself says
        so); service problems raise RoutingError('times_unavailable').
        """
        cfg = _MODES.get(mode)
        if cfg is None:
            raise RoutingError("invalid_mode", f"Unsupported travel mode: {mode}")

        key = (
            "table", cfg["server"], _round(from_lat), _round(from_lon),
            tuple((_round(a), _round(b)) for a, b in destinations),
        )
        hit = _table_cache.get(key)
        if hit is not None:
            value, at = hit
            if time.monotonic() - at < TABLE_FRESH_TTL_SECONDS:
                return value
            _table_cache.pop(key, None)

        coords = [f"{from_lon:.6f},{from_lat:.6f}"]
        coords += [f"{lon:.6f},{lat:.6f}" for lat, lon in destinations]
        url = (
            f"{self._base_url}/{cfg['server']}/table/v1/{cfg['profile']}/{';'.join(coords)}"
            f"?annotations=duration&sources=0"
        )
        payload = await self._fetch_json(url, error_kind="times_unavailable")
        rows = payload.get("durations") if isinstance(payload, dict) else None
        row = rows[0] if isinstance(rows, list) and rows else None
        if payload.get("code") != "Ok" or not isinstance(row, list) or len(row) < len(destinations) + 1:
            raise RoutingError("times_unavailable", "The routing service could not compute travel times.")

        # Row 0 is the origin itself; the rest align 1:1 with `destinations`.
        value = [None if sec is None else max(1, round(float(sec) / 60.0)) for sec in row[1 : len(destinations) + 1]]
        _evict_if_needed(_table_cache)
        _table_cache[key] = (value, time.monotonic())
        log.info("routing.table mode=%s destinations=%d", mode, len(destinations))
        return value

    # --- internals ----------------------------------------------------------

    async def _get_once(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            return await client.get(url)

    async def _fetch_json(self, url: str, *, error_kind: str, allow_retry: bool = True) -> dict:
        try:
            response = await self._get_once(url)
        except httpx.TimeoutException as exc:
            log.warning("routing.timeout")
            raise RoutingError("upstream_unavailable", "The routing service did not respond in time. Please try again shortly.") from exc
        except httpx.HTTPError as exc:
            log.warning("routing.connection_error type=%s", type(exc).__name__)
            raise RoutingError("upstream_unavailable", "Could not reach the routing service. Please try again shortly.") from exc

        if response.status_code == 429 and allow_retry:
            # Shared-IP throttling: one jittered retry absorbs FOSSGIS's
            # per-minute burst windows (same philosophy as the Open-Meteo
            # weather provider). Persistent limiting then surfaces as 503 and
            # the failure cache keeps us from hammering.
            delay = 2.5 + random.random()
            log.info("routing.rate_limited retry_in=%.1fs", delay)
            await asyncio.sleep(delay)
            return await self._fetch_json(url, error_kind=error_kind, allow_retry=False)

        if response.status_code == 400:
            # OSRM rejects malformed/out-of-range coordinates with 400.
            raise RoutingError("invalid_coordinates", "The routing service rejected the requested coordinates.")

        if response.status_code == 429:
            # Still throttled after the retry: FOSSGIS's per-minute bucket is
            # exhausted. 503 + failure-cache is the honest answer — the server
            # will succeed on a later window, and everyone shares that wait.
            log.warning("routing.still_rate_limited")
            raise RoutingError("upstream_unavailable", "The routing service is rate-limiting requests right now. Please try again shortly.")

        if response.status_code >= 400:
            log.warning("routing.http_error status=%s", response.status_code)
            raise RoutingError(error_kind, f"The routing service returned an error (HTTP {response.status_code}).")

        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("routing.malformed_json")
            raise RoutingError(error_kind, "The routing service returned an unreadable response.") from exc

        if not isinstance(payload, dict):
            raise RoutingError(error_kind, "The routing service returned an unreadable response.")
        return payload
