from fastapi import APIRouter, HTTPException, Query

from app.core.logging import get_logger
from app.schemas.schemas import GeoSearchResponse
from app.services.weather.geocoding import GeoCodingError, OpenMeteoGeoCoder

router = APIRouter(prefix="/geo", tags=["geo"])
log = get_logger(__name__)

# Error kinds -> clean HTTP codes (mirrors the weather router mapping).
_STATUS_BY_KIND = {
    "upstream_unavailable": 503,
    "upstream_error": 502,
    "malformed_response": 502,
}


@router.get("/search", response_model=GeoSearchResponse)
async def search_locations(
    query: str = Query(..., min_length=1, max_length=100, description="Place name, e.g. 'Mumbai'"),
    count: int = Query(5, ge=1, le=10, description="Maximum results"),
):
    """Key-less place-name search (Open-Meteo Geocoding API, GeoNames).

    Returns latitude/longitude ready for the existing weather/risk/safety
    endpoints. Unknown place names are a valid empty result, not an error.
    """
    coder = OpenMeteoGeoCoder()
    try:
        places = await coder.search(query, count=count)
    except GeoCodingError as exc:
        status = _STATUS_BY_KIND.get(exc.kind, 502)
        log.warning("geo.search_failed kind=%s status=%s", exc.kind, status)
        raise HTTPException(status_code=status, detail=exc.detail) from None

    log.info("geo.search query=%r results=%d", query, len(places))
    return GeoSearchResponse(
        query=query,
        results=[
            {
                "name": p.name,
                "label": p.label,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "country": p.country,
                "admin1": p.admin1,
                "timezone": p.timezone,
            }
            for p in places
        ],
    )
