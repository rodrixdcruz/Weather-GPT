import math

from fastapi import APIRouter, Query

from app.schemas.schemas import SafeZone

router = APIRouter(prefix="/safe-zones", tags=["safe-zones"])

# TODO: replace with a real government/NDMA shelter registry (Postgres
# table + admin ingestion), which is why `is_verified` exists per-record.
_FIXTURE_SHELTERS = [
    {"name": "Municipal Community Hall", "lat_offset": 0.01, "lon_offset": 0.01, "is_verified": True},
    {"name": "Govt. Senior Secondary School", "lat_offset": -0.015, "lon_offset": 0.008, "is_verified": True},
    {"name": "District Sports Complex", "lat_offset": 0.02, "lon_offset": -0.012, "is_verified": False},
    {"name": "Primary Health Centre", "lat_offset": -0.008, "lon_offset": -0.018, "is_verified": True},
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/nearby", response_model=list[SafeZone])
async def get_nearby_safe_zones(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    zones = []
    for s in _FIXTURE_SHELTERS:
        slat, slon = latitude + s["lat_offset"], longitude + s["lon_offset"]
        zones.append(
            SafeZone(
                name=s["name"],
                latitude=slat,
                longitude=slon,
                distance_km=round(_haversine_km(latitude, longitude, slat, slon), 2),
                is_verified=s["is_verified"],
            )
        )
    return sorted(zones, key=lambda z: z.distance_km)
