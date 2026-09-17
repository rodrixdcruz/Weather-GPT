// Keyless road routing via FOSSGIS's public OSRM instance — the same servers
// that power directions on openstreetmap.org. Free, no API key, CORS-open to
// browsers (verified). Usage here is one request per user click, well within
// their fair-use policy.
const OSRM_CONFIG = {
  driving: { server: 'routed-car', profile: 'driving' },
  walking: { server: 'routed-foot', profile: 'foot' },
}

const TIMEOUT_MS = 12000

/**
 * Fetch a road route between two points. Resolves
 * `{ coords, distanceKm, durationMin }` where `coords` are Leaflet
 * [lat, lon] pairs. Rejects with Error('no_route') when the network exists
 * but that travel mode cannot traverse it (e.g. no footpath connection), or
 * Error('route_unavailable') for upstream/network problems — callers show a
 * friendly message and keep the Google Maps handoff available.
 */
export async function fetchRoute(from, to, mode = 'driving', { signal } = {}) {
  const cfg = OSRM_CONFIG[mode] || OSRM_CONFIG.driving
  const fmt = (v) => Number(v).toFixed(6)
  const path = `${fmt(from.longitude)},${fmt(from.latitude)};${fmt(to.longitude)},${fmt(to.latitude)}`
  const url =
    `https://routing.openstreetmap.de/${cfg.server}/route/v1/${cfg.profile}/${path}` +
    `?overview=full&geometries=geojson&alternatives=false&steps=false`

  // One timeout controller merges the caller's signal (component unmount /
  // re-route) with our own deadline, so a hanging request never pins the UI.
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const res = await fetch(url, { signal: controller.signal })
    if (!res.ok) throw new Error('route_unavailable', { cause: res.status })
    const data = await res.json()
    const route = data?.routes?.[0]
    if (data?.code !== 'Ok' || !route?.geometry?.coordinates?.length) throw new Error('no_route')
    return {
      coords: route.geometry.coordinates.map(([lon, lat]) => [lat, lon]),
      distanceKm: route.distance / 1000,
      durationMin: Math.max(1, Math.round(route.duration / 60)),
    }
  } catch (err) {
    if (err?.name === 'AbortError') throw new Error('route_unavailable', { cause: err })
    throw err
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }
}
