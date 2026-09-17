import { useCallback, useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Circle, Popup, Polyline, useMap } from 'react-leaflet'
import { t } from '../i18n'
import { DirectionsLink, TravelModeToggle, mapsDirectionsUrl } from './SidePanels'
import { fetchRoute } from '../lib/routing'

// Default view span: zoom 13 ≈ a neighborhood/city-block view.
const DEFAULT_ZOOM = 13

/**
 * Keeps the map locked onto the live location: recenters (flyTo) whenever
 * `center` changes — including geolocation "Use my location" updates —
 * so the pin always marks where the user actually is.
 */
function MapAutoCenter({ center, zoom = DEFAULT_ZOOM }) {
  const map = useMap()
  useEffect(() => {
    if (!center || !Number.isFinite(center.latitude) || !Number.isFinite(center.longitude)) return
    map.flyTo([center.latitude, center.longitude], zoom, { duration: 0.8 })
  }, [center, zoom, map])
  return null
}

/**
 * Leaflet's absolutely-positioned panes use high z-indexes (up to 1000)
 * that paint over sibling cards in the surrounding CSS grid. Applying
 * `isolation: isolate` to the map container creates a local stacking
 * context, so Leaflet's z-indexes compete only inside this card.
 */
function StackingIsolation() {
  const map = useMap()
  useEffect(() => {
    const container = map.getContainer()
    container.style.isolation = 'isolate'
    return () => {
      container.style.isolation = ''
    }
  }, [map])
  return null
}

/** Leaflet needs an explicit nudge when its container resizes/claims layout. */
function SizeInvalidator() {
  const map = useMap()
  useEffect(() => {
    const id = window.setTimeout(() => map.invalidateSize(), 150)
    return () => window.clearTimeout(id)
  }, [map])
  return null
}

/** Fits the viewport around the active route so both endpoints stay visible. */
function RouteFitBounds({ coords }) {
  const map = useMap()
  useEffect(() => {
    if (coords?.length > 1) {
      map.flyToBounds(coords, { padding: [30, 30], duration: 0.8 })
    }
  }, [coords, map])
  return null
}

/**
 * The active route lives in App (shared by the map and the shelter list);
 * this component owns the fetch + drawing. Re-runs when the target, the
 * travel mode, or the user's location changes, so the line always reflects
 * the current origin and profile. Stale responses are ignored via abort.
 */
export default function MapCard({ center, safeZones = [], travelMode = 'driving', onTravelModeChange, activeRoute, onDirections, language }) {
  const [route, setRoute] = useState(null)
  const routeAbortRef = useRef(null)

  useEffect(() => {
    routeAbortRef.current?.abort()
    if (!activeRoute || !center) {
      setRoute(null)
      return
    }
    const controller = new AbortController()
    routeAbortRef.current = controller
    // Paint the panel instantly (loading state); geometry arrives when OSRM answers.
    setRoute({ from: center, to: activeRoute.to, targetName: activeRoute.name, loading: true })
    fetchRoute(center, activeRoute.to, travelMode, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return
        setRoute((prev) => (prev && prev.to === activeRoute.to ? { ...prev, ...result, loading: false } : prev))
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setRoute((prev) => (prev && prev.to === activeRoute.to ? { ...prev, error: true, loading: false } : prev))
      })
    return () => controller.abort()
  }, [activeRoute, travelMode, center])

  const showDirections = useCallback(
    (target, name) => onDirections?.({ to: target, name }),
    [onDirections],
  )

  const closeRoute = useCallback(() => onDirections?.(null), [onDirections])

  if (!center) return null

  return (
    <div
      className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl overflow-hidden relative p-0 min-h-[360px]"
      style={{ isolation: 'isolate' }}
    >
      <div className="absolute top-2.5 left-2.5 z-[1000] bg-navy-950/85 border border-border rounded-lg px-3 py-1.5 text-[11.5px] font-semibold">
        {t(language, 'nearbySafeZones')}
      </div>
      {safeZones.length > 0 && (
        <div className="absolute top-2.5 right-2.5 z-[1000]">
          <TravelModeToggle mode={travelMode} onChange={onTravelModeChange} language={language} />
        </div>
      )}
      <MapContainer
        center={[center.latitude, center.longitude]}
        zoom={DEFAULT_ZOOM}
        style={{ height: '100%', minHeight: 360, filter: 'saturate(0.85) brightness(0.92)' }}
      >
        <MapAutoCenter center={center} />
        <StackingIsolation />
        <SizeInvalidator />
        {route && <RouteFitBounds coords={route.coords} />}
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CircleMarker
          center={[center.latitude, center.longitude]}
          radius={8}
          pathOptions={{ color: '#3aa0ff', fillOpacity: 0.8 }}
        >
          <Popup>You are here</Popup>
        </CircleMarker>
        {/* ~350 m ring around the live position for at-a-glance accuracy. */}
        <Circle
          center={[center.latitude, center.longitude]}
          radius={350}
          pathOptions={{ color: '#3aa0ff', fillColor: '#3aa0ff', fillOpacity: 0.08, weight: 1 }}
        />
        {safeZones.map((z) => (
          <CircleMarker
            key={z.name}
            center={[z.latitude, z.longitude]}
            radius={7}
            pathOptions={{ color: z.is_verified ? '#22c55e' : '#eab308', fillOpacity: 0.8 }}
          >
            <Popup>
              <div className="min-w-[180px] font-sans">
                <div className="font-semibold text-[13px] text-slate-100">{z.name}</div>
                <div className="text-[11px] text-slate-300 mb-1.5">
                  {z.distance_km} km · {z.is_verified ? t(language, 'verified') : t(language, 'estimate')}
                </div>
                <DirectionsLink
                  from={center}
                  to={z}
                  name={z.name}
                  mode={travelMode}
                  language={language}
                  onDirections={showDirections}
                  className="inline-block text-[11px] font-semibold px-2.5 py-1 rounded bg-sky/15 text-sky border border-sky/40 hover:bg-sky/25 transition-colors"
                />
              </div>
            </Popup>
          </CircleMarker>
        ))}
        {route && !route.loading && !route.error && (
          <>
            {/* Casing + core so the line reads clearly over any basemap. */}
            <Polyline positions={route.coords} pathOptions={{ color: '#0b1730', weight: 9, opacity: 0.45 }} interactive={false} />
            <Polyline positions={route.coords} pathOptions={{ color: '#3aa0ff', weight: 4, opacity: 0.95 }} interactive={false} />
          </>
        )}
      </MapContainer>
      {route && (
        <RoutePanel
          route={route}
          targetName={route.targetName}
          travelMode={travelMode}
          language={language}
          onClose={closeRoute}
        />
      )}
      <div className="absolute bottom-2.5 left-2.5 z-[1000] bg-navy-950/85 border border-border rounded-lg px-3 py-2 text-[11px] flex gap-3 flex-wrap">
        <Legend color="#3aa0ff" label={t(language, 'you')} />
        <Legend color="#22c55e" label={t(language, 'verifiedShelter')} />
        <Legend color="#eab308" label={t(language, 'unverifiedShelter')} />
      </div>
    </div>
  )
}

/** Absolutely-positioned route info card (lives above the map, below overlays). */
function RoutePanel({ route, targetName, travelMode, language, onClose }) {
  return (
    <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-[1100] bg-navy-950/95 border border-border rounded-xl px-3.5 py-2.5 shadow-xl flex items-center gap-3 whitespace-nowrap">
      <div className="flex flex-col">
        <div className="text-[12px] font-semibold truncate max-w-[220px]">{targetName}</div>
        <div className="text-[11px] text-slate-300">
          {route.loading
            ? t(language, 'routeLoading')
            : route.error
              ? t(language, 'routeFailed')
              : `${route.distanceKm.toFixed(1)} km · ${route.durationMin} ${t(language, 'routeMinutes')} · ${t(language, travelMode)}`
          }
        </div>
      </div>
      {!route.loading && !route.error && (
        <a
          href={mapsDirectionsUrl(route.from, route.to, travelMode)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] font-semibold px-2.5 py-1 rounded bg-sky/15 text-sky border border-sky/40 hover:bg-sky/25 transition-colors whitespace-nowrap"
        >
          ➤ {t(language, 'directions')}
        </a>
      )}
      <button
        type="button"
        onClick={onClose}
        title={t(language, 'routeClose')}
        className="text-slate-300 hover:text-slate-100 text-[15px] leading-none px-1"
      >
        ✕
      </button>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
      {label}
    </div>
  )
}
