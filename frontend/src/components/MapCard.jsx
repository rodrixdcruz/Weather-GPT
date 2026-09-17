import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Circle, Popup, useMap } from 'react-leaflet'
import { t } from '../i18n'
import { DirectionsLink } from './SidePanels'

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

export default function MapCard({ center, safeZones = [], language }) {
  if (!center) return null

  return (
    <div
      className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl overflow-hidden relative p-0 min-h-[360px]"
      style={{ isolation: 'isolate' }}
    >
      <div className="absolute top-2.5 left-2.5 z-[1000] bg-navy-950/85 border border-border rounded-lg px-3 py-1.5 text-[11.5px] font-semibold">
        {t(language, 'nearbySafeZones')}
      </div>
      <MapContainer
        center={[center.latitude, center.longitude]}
        zoom={DEFAULT_ZOOM}
        style={{ height: '100%', minHeight: 360, filter: 'saturate(0.85) brightness(0.92)' }}
      >
        <MapAutoCenter center={center} />
        <StackingIsolation />
        <SizeInvalidator />
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
                  language={language}
                  className="inline-block text-[11px] font-semibold px-2.5 py-1 rounded bg-sky/15 text-sky border border-sky/40 hover:bg-sky/25 transition-colors"
                />
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="absolute bottom-2.5 left-2.5 z-[1000] bg-navy-950/85 border border-border rounded-lg px-3 py-2 text-[11px] flex gap-3 flex-wrap">
        <Legend color="#3aa0ff" label={t(language, 'you')} />
        <Legend color="#22c55e" label={t(language, 'verifiedShelter')} />
        <Legend color="#eab308" label={t(language, 'unverifiedShelter')} />
      </div>
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
