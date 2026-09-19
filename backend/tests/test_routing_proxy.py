"""Tests for the backend OSRM routing proxy.

All upstream HTTP is mocked via httpx.MockTransport — mirroring the
air-quality/geo test conventions — so no test ever hits the real FOSSGIS
servers. Covers the service layer (normalization, caching, retry, errors)
and both endpoints' status-code mapping.
"""
import httpx
import pytest


def _route_ok() -> dict:
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": 2000.0,
                "duration": 240.0,
                "geometry": {"coordinates": [[72.87, 19.07], [72.875, 19.074], [72.88, 19.08]]},
            }
        ],
    }


def _table_ok() -> dict:
    # One source row: origin itself (0), then two destinations — one
    # reachable (180 s), one unreachable (null, as OSRM reports it).
    return {"code": "Ok", "durations": [[0.0, 180.0, None]]}


def _service(handler) -> object:
    from app.services.routing.osrm import OsrmRoutingService

    return OsrmRoutingService(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _clean_routing_caches():
    from app.services.routing.osrm import reset_routing_caches

    reset_routing_caches()
    yield
    reset_routing_caches()


class TestRouteService:
    async def test_route_normalized_to_leaflet_shape(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=_route_ok())

        route = await _service(handler).get_route(19.07, 72.87, 19.08, 72.88, "walking")
        assert route["distance_km"] == 2.0
        assert route["duration_min"] == 4
        assert route["coordinates"] == [[19.07, 72.87], [19.074, 72.875], [19.08, 72.88]]
        # Foot mode goes to the routed-foot host with the foot profile, and
        # OSRM wants lon,lat order in the path.
        assert "routed-foot" in str(seen[0].url)
        assert "/foot/" in str(seen[0].url)
        assert "72.870000,19.070000" in str(seen[0].url)

    async def test_identifies_itself_to_fossgis(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["ua"] = request.headers.get("user-agent", "")
            return httpx.Response(200, json=_route_ok())

        await _service(handler).get_route(19.07, 72.87, 19.08, 72.88, "driving")
        assert "MausamBagha AI" in captured["ua"]

    async def test_second_call_same_cell_served_from_cache(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_route_ok())

        svc = _service(handler)
        first = await svc.get_route(19.071, 72.871, 19.08, 72.88, "driving")
        # ~110 m cell rounding: a sub-cell jitter must reuse the cache.
        second = await svc.get_route(19.0712, 72.8708, 19.08, 72.88, "driving")
        assert calls["n"] == 1
        assert first == second

    async def test_different_mode_is_a_cache_miss(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_route_ok())

        svc = _service(handler)
        await svc.get_route(19.07, 72.87, 19.08, 72.88, "driving")
        await svc.get_route(19.07, 72.87, 19.08, 72.88, "walking")
        assert calls["n"] == 2

    async def test_429_retried_once_then_success(self, monkeypatch):
        calls = {"n": 0}

        async def fake_sleep(_):
            return None

        monkeypatch.setattr("app.services.routing.osrm.asyncio.sleep", fake_sleep)

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={"error": "slow down"})
            return httpx.Response(200, json=_route_ok())

        route = await _service(handler).get_route(19.07, 72.87, 19.08, 72.88, "driving")
        assert route["duration_min"] == 4
        assert calls["n"] == 2

    async def test_429_twice_surfaces_as_upstream_unavailable(self, monkeypatch):
        async def fake_sleep(_):
            return None

        monkeypatch.setattr("app.services.routing.osrm.asyncio.sleep", fake_sleep)
        svc = _service(lambda request: httpx.Response(429, json={"error": "slow down"}))
        with pytest.raises(Exception) as excinfo:
            await svc.get_route(19.07, 72.87, 19.08, 72.88, "driving")
        assert excinfo.value.kind == "upstream_unavailable"

    async def test_connection_refused_is_upstream_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        with pytest.raises(Exception) as excinfo:
            await _service(handler).get_route(19.07, 72.87, 19.08, 72.88, "driving")
        assert excinfo.value.kind == "upstream_unavailable"

    async def test_upstream_500_maps_to_service_error(self):
        svc = _service(lambda request: httpx.Response(500, text="boom"))
        with pytest.raises(Exception) as excinfo:
            await svc.get_route(19.07, 72.87, 19.08, 72.88, "driving")
        assert excinfo.value.kind == "route_unavailable"

    async def test_no_network_for_mode_is_no_route(self):
        svc = _service(lambda request: httpx.Response(200, json={"code": "NoRoute", "routes": []}))
        with pytest.raises(Exception) as excinfo:
            await svc.get_route(19.07, 72.87, 19.08, 72.88, "walking")
        assert excinfo.value.kind == "no_route"

    async def test_unknown_mode_rejected_before_any_http(self):
        from app.services.routing.osrm import RoutingError

        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("no upstream call expected")

        with pytest.raises(RoutingError) as excinfo:
            await _service(handler).get_route(19.07, 72.87, 19.08, 72.88, "flying")
        assert excinfo.value.kind == "invalid_mode"


class TestTravelTimesService:
    async def test_minutes_rounded_and_nulls_preserved(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json=_table_ok())

        times = await _service(handler).get_travel_times(
            19.07, 72.87, [(19.08, 72.88), (19.09, 72.89)], "walking"
        )
        assert times == [3, None]
        assert "routed-foot" in seen[0] and "annotations=duration" in seen[0]

    async def test_table_result_cached(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_table_ok())

        svc = _service(handler)
        first = await svc.get_travel_times(19.07, 72.87, [(19.08, 72.88)], "driving")
        second = await svc.get_travel_times(19.07, 72.87, [(19.08, 72.88)], "driving")
        assert calls["n"] == 1
        assert first == second == [3]

    async def test_bad_upstream_shape_is_times_unavailable(self):
        svc = _service(lambda request: httpx.Response(200, json={"code": "Ok", "durations": []}))
        with pytest.raises(Exception) as excinfo:
            await svc.get_travel_times(19.07, 72.87, [(19.08, 72.88)], "driving")
        assert excinfo.value.kind == "times_unavailable"


class TestRoutingEndpoints:
    async def test_route_endpoint_happy_path(self, client, monkeypatch):
        from app.api.v1.routers import routing as routing_router

        class StubSvc:
            async def get_route(self, *args, **kwargs):
                return {"distance_km": 2.0, "duration_min": 4, "coordinates": [[19.07, 72.87]]}

        monkeypatch.setattr(routing_router, "OsrmRoutingService", lambda: StubSvc())
        response = await client.get(
            "/api/v1/routing/route?from_lat=19.07&from_lon=72.87&to_lat=19.08&to_lon=72.88&mode=driving"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["distance_km"] == 2.0
        assert body["coordinates"][0] == [19.07, 72.87]

    async def test_no_route_is_404(self, client, monkeypatch):
        from app.api.v1.routers import routing as routing_router
        from app.services.routing.osrm import RoutingError

        class StubSvc:
            async def get_route(self, *args, **kwargs):
                raise RoutingError("no_route", "No road route exists between these points for this travel mode.")

        monkeypatch.setattr(routing_router, "OsrmRoutingService", lambda: StubSvc())
        response = await client.get(
            "/api/v1/routing/route?from_lat=19.07&from_lon=72.87&to_lat=19.08&to_lon=72.88"
        )
        assert response.status_code == 404

    async def test_upstream_outage_is_503(self, client, monkeypatch):
        from app.api.v1.routers import routing as routing_router
        from app.services.routing.osrm import RoutingError

        class StubSvc:
            async def get_route(self, *args, **kwargs):
                raise RoutingError("upstream_unavailable", "Could not reach the routing service.")

        monkeypatch.setattr(routing_router, "OsrmRoutingService", lambda: StubSvc())
        response = await client.get(
            "/api/v1/routing/route?from_lat=19.07&from_lon=72.87&to_lat=19.08&to_lon=72.88"
        )
        assert response.status_code == 503

    async def test_bad_mode_rejected(self, client):
        response = await client.get(
            "/api/v1/routing/route?from_lat=19.07&from_lon=72.87&to_lat=19.08&to_lon=72.88&mode=helicopter"
        )
        assert response.status_code == 422

    async def test_out_of_range_coordinates_rejected(self, client):
        response = await client.get(
            "/api/v1/routing/route?from_lat=190&from_lon=72.87&to_lat=19.08&to_lon=72.88"
        )
        assert response.status_code == 422

    async def test_travel_times_endpoint_happy_path(self, client, monkeypatch):
        from app.api.v1.routers import routing as routing_router

        class StubSvc:
            async def get_travel_times(self, _lat, _lon, destinations, mode):
                return [3, None]

        monkeypatch.setattr(routing_router, "OsrmRoutingService", lambda: StubSvc())
        response = await client.get(
            "/api/v1/routing/travel-times?from_lat=19.07&from_lon=72.87&to_lat=19.08,72.88;19.09,72.89&mode=walking"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "walking"
        assert body["minutes"] == [3, None]

    async def test_travel_times_rejects_malformed_destination(self, client):
        response = await client.get(
            "/api/v1/routing/travel-times?from_lat=19.07&from_lon=72.87&to_lat=19.08"
        )
        assert response.status_code == 422

    async def test_travel_times_rejects_out_of_range_destination(self, client):
        response = await client.get(
            "/api/v1/routing/travel-times?from_lat=19.07&from_lon=72.87&to_lat=19.08,720"
        )
        assert response.status_code == 422

    async def test_travel_times_caps_destination_count(self, client):
        to_lat = ";".join(f"19.0{i % 10},72.8{i % 10}" for i in range(26))
        response = await client.get(
            f"/api/v1/routing/travel-times?from_lat=19.07&from_lon=72.87&to_lat={to_lat}"
        )
        assert response.status_code == 422

    async def test_travel_times_upstream_failure_is_502(self, client, monkeypatch):
        from app.api.v1.routers import routing as routing_router
        from app.services.routing.osrm import RoutingError

        class StubSvc:
            async def get_travel_times(self, *args, **kwargs):
                raise RoutingError("times_unavailable", "The routing service could not compute travel times.")

        monkeypatch.setattr(routing_router, "OsrmRoutingService", lambda: StubSvc())
        response = await client.get(
            "/api/v1/routing/travel-times?from_lat=19.07&from_lon=72.87&to_lat=19.08,72.88"
        )
        assert response.status_code == 502
