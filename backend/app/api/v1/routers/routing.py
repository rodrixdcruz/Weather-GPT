from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.schemas.schemas import RoutingResponse, TravelTimesResponse
from app.services.routing.osrm import OsrmRoutingService, RoutingError, reset_routing_caches

router = APIRouter(prefix="/routing", tags=["routing"])
log = get_logger(__name__)

# Error kinds -> clean HTTP codes (mirrors the weather/geo routers).
_STATUS_BY_KIND = {
    "invalid_mode": 422,
    "invalid_coordinates": 422,
    "no_route": 404,
    "upstream_unavailable": 503,
    "upstream_error": 502,
    "malformed_response": 502,
    "times_unavailable": 502,
}

# The endpoint is public (unauthenticated) like the other read-only data
# tiers, so the coordinate surface is bounded: valid Earth only, and at most
# 25 destinations per table request (the app's shelter lists are small; the
# cap keeps a single request from fanning out into a big upstream call).
_MAX_DESTINATIONS = 25


@router.get("/route", response_model=RoutingResponse)
async def get_route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
    mode: str = Query("driving", pattern="^(driving|walking)$"),
):
    """Road route between two points, proxied through OSRM with caching.

    Coordinates come back in [lat, lon] order, ready for Leaflet. 404 means
    genuinely no road for that mode (e.g. no footpath across a river) — the
    client keeps its external-maps handoff for that case.

    Responses carry Cache-Control: public with a short max-age: routes are
    point-in-time traffic estimates, and the server-side TTL cache already
    absorbs repeat load upstream.
    """
    service = OsrmRoutingService()
    try:
        route = await service.get_route(from_lat, from_lon, to_lat, to_lon, mode)
    except RoutingError as exc:
        status = _STATUS_BY_KIND.get(exc.kind, 502)
        log.warning("routing.route_failed kind=%s status=%s", exc.kind, status)
        raise HTTPException(status_code=status, detail=exc.detail) from None

    log.info(
        "routing.route served mode=%s duration_min=%s distance_km=%s",
        mode, route["duration_min"], route["distance_km"],
    )
    response = RoutingResponse(
        distance_km=route["distance_km"],
        duration_min=route["duration_min"],
        coordinates=route["coordinates"],
    )
    # 60 s client-side reuse: the server cache owns longer-term dedup, this
    # just stops a single user's quick re-click from re-traversing the proxy.
    return JSONResponse(
        content=response.model_dump(mode="json"),
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/travel-times", response_model=TravelTimesResponse)
async def get_travel_times(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: str = Query(..., description="Comma-separated lat,lon pairs, e.g. '19.1,72.87;19.05,72.9'"),
    mode: str = Query("driving", pattern="^(driving|walking)$"),
):
    """Minutes from one origin to many destinations in one OSRM table request.

    Powers the shelter list's per-mode travel-time badges with a single
    upstream call. Entries are minutes aligned 1:1 with the requested
    destinations; None marks a destination unreachable on that network.
    """
    destinations: list[tuple[float, float]] = []
    for chunk in to_lat.split(";"):
        parts = chunk.split(",")
        if len(parts) != 2:
            raise HTTPException(status_code=422, detail="Each destination must be 'lat,lon', separated by ';'.")
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            raise HTTPException(status_code=422, detail="Destination coordinates must be numbers.") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(status_code=422, detail="Destination coordinates out of range.")
        destinations.append((lat, lon))

    if not destinations:
        raise HTTPException(status_code=422, detail="At least one destination is required.")
    if len(destinations) > _MAX_DESTINATIONS:
        raise HTTPException(status_code=422, detail=f"At most {_MAX_DESTINATIONS} destinations per request.")

    service = OsrmRoutingService()
    try:
        minutes = await service.get_travel_times(from_lat, from_lon, destinations, mode)
    except RoutingError as exc:
        status = _STATUS_BY_KIND.get(exc.kind, 502)
        log.warning("routing.times_failed kind=%s status=%s", exc.kind, status)
        raise HTTPException(status_code=status, detail=exc.detail) from None

    log.info("routing.times served mode=%s destinations=%d", mode, len(destinations))
    return TravelTimesResponse(mode=mode, minutes=minutes)


__all__ = ["router", "reset_routing_caches"]
