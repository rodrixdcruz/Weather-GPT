/**
 * Lightweight decorative map layer — pure SVG, no tile service, no iframe.
 * Renders a location-centered graticule so the marker position is derived
 * from real lat/lon (any point on Earth works, not a fixed country box),
 * and labels the locale from location_label when available.
 */
export function resolveLocation(location = {}) {
  const lat = Number(location.lat ?? location.latitude ?? NaN)
  const lon = Number(location.lon ?? location.longitude ?? NaN)
  const label =
    (location.label || location.location_label || '').trim() ||
    (Number.isFinite(lat) && Number.isFinite(lon)
      ? `Lat ${lat.toFixed(2)}, Lon ${lon.toFixed(2)}`
      : '')
  return { lat, lon, label }
}

/**
 * Project a lat/lon into the map square using an equirectangular projection
 * centered on the location, so the marker sits near the middle of the canvas
 * and coordinates genuinely correspond to the selected point.
 */
export function projectToPosition(lat, lon, center, spanDeg = 8) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !center) {
    return { left: '50%', top: '46%' }
  }
  const spanY = spanDeg / 2
  const spanX = spanY / Math.max(0.2, Math.cos((center.lat * Math.PI) / 180))
  const nx = 0.5 + (lon - center.lon) / (2 * spanX)
  const ny = 0.5 - (lat - center.lat) / (2 * spanY)
  const clamp01 = (v) => Math.min(0.97, Math.max(0.03, v))
  return { left: `${clamp01(nx) * 100}%`, top: `${clamp01(ny) * 100}%` }
}

export default function MapCanvas({ location }) {
  const { lat, lon, label } = resolveLocation(location)
  const hasCenter = Number.isFinite(lat) && Number.isFinite(lon)
  // Graticule labels centered on the location (or 0,0 fallback).
  const cLat = hasCenter ? lat : 0
  const cLon = hasCenter ? lon : 0
  const fmt = (v) => `${Math.abs(v).toFixed(1)}°${v >= 0 ? 'N' : 'S'}`
  const fmtLon = (v) => `${Math.abs(v).toFixed(1)}°${v >= 0 ? 'E' : 'W'}`

  return (
    <div className="map-canvas" role="presentation">
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="wgtp-land" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#dce9d5" />
            <stop offset="55%" stopColor="#c3d5bd" />
            <stop offset="100%" stopColor="#e8e0c6" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="1000" height="1000" fill="url(#wgtp-land)" />
        <g className="map-grid" stroke="rgba(120,140,120,.16)" strokeWidth="2">
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => <line key={`v${i}`} x1={i * 100} y1="0" x2={i * 100} y2="1000" />)}
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => <line key={`h${i}`} x1="0" y1={i * 100} x2="1000" y2={i * 100} />)}
        </g>
        <path className="map-river" d="M120 0 C 260 180 220 320 420 480 360 640 560 840 520 1000" fill="none" stroke="#9fc3e8" strokeWidth="26" opacity=".55" />
        <path className="map-river" d="M120 0 C 260 180 220 320 420 480 360 640 560 840 520 1000" fill="none" stroke="#dff0ff" strokeWidth="10" opacity=".5" />
        <g className="map-roads" stroke="rgba(255,255,255,.5)" strokeWidth="7" fill="none">
          <path d="M-50 780 L 1050 260" />
          <path d="M120 -40 L 880 1040" />
          <path d="M-80 220 L 760 1080" />
        </g>
        <g className="map-roads-minor" stroke="rgba(242,217,139,.6)" strokeWidth="3" fill="none">
          <path d="M300 90 L 420 640 L 640 470 L 820 600" />
          <path d="M560 -20 L 700 460 L 540 760" />
        </g>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x={80 + i * 150} y={90 + ((i * 61) % 420)} width="34" height="22" rx="6" fill="rgba(158,180,130,.32)" />
        ))}
        {hasCenter ? (
          <g fill="rgba(20,32,60,.5)" fontFamily="system-ui" fontSize="22">
            <text x="24" y="120">{fmt(cLat + 3)}</text>
            <text x="24" y="930">{fmt(cLat - 3)}</text>
            <text x="760" y="540">{fmtLon(cLon + 3)}</text>
          </g>
        ) : null}
        <text x="500" y="980" textAnchor="middle" fontSize="24" fill="rgba(20,32,60,.45)" fontFamily="system-ui">MausamBagha AI · LIVE MAP</text>
      </svg>
      {label ? <span className="map-canvas-locale">{label}</span> : null}
    </div>
  )
}
