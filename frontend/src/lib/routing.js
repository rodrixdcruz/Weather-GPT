// Road routing, served by the backend's OSRM proxy (/api/v1/routing/*).
//
// The browser no longer talks to FOSSGIS directly: every visitor used to
// spend the shared per-IP fair-use budget independently, with nothing shared
// between them. Now all clients funnel through the backend, which caches
// per ~110 m cell + travel mode process-wide, retries transient throttles
// once, and identifies itself to FOSSGIS with a proper User-Agent.
//
// The exported signatures and error strings are unchanged from the original
// direct-to-OSRM client, so no consumer (MapCard, SidePanels) had to move.
import { api } from './api'

const TIMEOUT_MS = 20000 // backend does its own 8s-per-attempt retry; leave headroom

/**
 * Fetch a road route between two points. Resolves
 * `{ coords, distanceKm, durationMin }` where `coords` are Leaflet
 * [lat, lon] pairs. Rejects with Error('no_route') when the network exists
 * but that travel mode cannot traverse it (e.g. no footpath connection), or
 * Error('route_unavailable') for upstream/network problems — callers show a
 * friendly message and keep the Google Maps handoff available.
 */
export async function fetchRoute(from, to, mode = 'driving', { signal } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const data = await api.getRoute({
      from_lat: from.latitude,
      from_lon: from.longitude,
      to_lat: to.latitude,
      to_lon: to.longitude,
      mode: mode === 'walking' ? 'walking' : 'driving',
      signal: controller.signal,
    })
    return {
      coords: data.coordinates,
      distanceKm: data.distance_km,
      durationMin: data.duration_min,
    }
  } catch (err) {
    if (err?.name === 'AbortError') throw new Error('route_unavailable', { cause: err })
    // 404 = OSRM answered "no road for this mode" (the backend maps it).
    if (err?.status === 404) throw new Error('no_route', { cause: err })
    throw new Error('route_unavailable', { cause: err })
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }
}

/**
 * Travel times from one origin to many destinations — one backend call,
 * which the backend serves from a single OSRM table request shared by every
 * visitor. Returns an array aligned with `destinations`, each entry minutes
 * rounded up, or null when that destination is unreachable on this travel
 * mode's network. Rejects with Error('times_unavailable') on upstream or
 * network problems; callers degrade to '—' badges.
 */
export async function fetchTravelTimes(origin, destinations, mode = 'driving', { signal } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const data = await api.getTravelTimes({
      from_lat: origin.latitude,
      from_lon: origin.longitude,
      to_lat: destinations.map((d) => `${d.latitude},${d.longitude}`).join(';'),
      mode: mode === 'walking' ? 'walking' : 'driving',
      signal: controller.signal,
    })
    return data.minutes
  } catch (err) {
    if (err?.name === 'AbortError') throw new Error('times_unavailable', { cause: err })
    throw new Error('times_unavailable', { cause: err })
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }
}
