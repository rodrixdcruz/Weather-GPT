import { useEffect, useRef, useState } from 'react'
import { formatTemperature, getWeatherUIState } from '../ui-state'
import MapContainer from './MapContainer'
import MapCanvas, { projectToPosition, resolveLocation } from './MapCanvas'
import MapWeatherOverlay from './MapWeatherOverlay'
import MapLocationMarker from './MapLocationMarker'
import MapPulse from './MapPulse'
import MapControls from './MapControls'
import WeatherInfoPanel from './WeatherInfoPanel'
import './reactive-map.css'

const DEMO_KEY = 'weathergpt.reactive-map.demo'
const MAX_ZOOM = 1.75

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

const clampZoom = (v) => Math.min(MAX_ZOOM, Math.max(1, Math.round(v * 100) / 100))

function targetSize() {
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (vw <= 640) return { width: vw * 0.94, height: Math.min(vh * 0.75, vw * 0.94), radius: 30 }
  if (vw <= 1024) return { width: vw * 0.92, height: Math.min(vh * 0.86, 760), radius: 44 }
  return { width: Math.min(vw * 0.88, 1440), height: Math.min(vh * 0.92, 900), radius: 55 }
}

export default function ReactiveMap({
  location = {},
  weather = {},
  risks = null,
  currentTime,
  uiState = null,
  autoDemo = false,
  defaultExpanded = false,
  onStateChange = null,
  mapLayer = null,
}) {
  const state = uiState || getWeatherUIState(weather || {}, risks || null, currentTime)
  const { lat, lon, label } = resolveLocation(location)

  const surfaceRef = useRef(null)
  const [expanded, setExpanded] = useState(false)
  const [fixed, setFixed] = useState(false)
  const [showScrim, setShowScrim] = useState(false)
  const [anchor, setAnchor] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [markerPos, setMarkerPos] = useState({ left: '50%', top: '46%' })
  const originRef = useRef({ x: 0, y: 0 })
  const animatingRef = useRef(false)
  // Latest open()/close() closures for timer/listener use without stale args.
  const openRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    setMarkerPos(
      Number.isFinite(lat) && Number.isFinite(lon)
        ? projectToPosition(lat, lon, { lat, lon })
        : { left: '50%', top: '46%' },
    )
  }, [lat, lon])

  /* ------------------------- geometry / morph ------------------------- */
  function open() {
    if (expanded || animatingRef.current) return
    const el = surfaceRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    originRef.current = { x: rect.left, y: rect.top }

    el.style.position = 'fixed'
    el.style.left = `${rect.left}px`
    el.style.top = `${rect.top}px`
    el.style.transition = 'none'
    setFixed(true)
    setShowScrim(true)
    void el.offsetWidth // commit the snap frame (no visual jump)
    el.style.transition = ''

    const size = targetSize()
    el.style.setProperty('--map-w', `${size.width}px`)
    el.style.setProperty('--map-h', `${size.height}px`)
    el.style.setProperty('--map-r', `${size.radius}px`)
    setExpanded(true)
    animatingRef.current = true

    window.requestAnimationFrame(() => {
      setAnchor({
        x: (window.innerWidth - size.width) / 2 - rect.left,
        y: (window.innerHeight - size.height) / 2 - rect.top,
      })
    })
  }

  function close() {
    if (!expanded || animatingRef.current) return
    const el = surfaceRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const origin = originRef.current
    setAnchor({ x: origin.x - rect.left, y: origin.y - rect.top })
    el.style.removeProperty('--map-w')
    el.style.removeProperty('--map-h')
    el.style.removeProperty('--map-r')
    setExpanded(false)
    animatingRef.current = true
  }
  openRef.current = open
  closeRef.current = close

  function releaseFixed() {
    const el = surfaceRef.current
    if (el) {
      el.style.position = ''
      el.style.left = ''
      el.style.top = ''
    }
    setFixed(false)
    setShowScrim(false)
    setZoom(1)
  }

  // `transform` animates on both open and close, so it is the reliable
  // single transition-end signal for the morph.
  function onSurfaceTransitionEnd(e) {
    if (e.target !== surfaceRef.current || e.propertyName !== 'transform') return
    animatingRef.current = false
    if (expanded) {
      if (onStateChange) onStateChange(true)
    } else {
      releaseFixed()
      setAnchor({ x: 0, y: 0 })
      if (onStateChange) onStateChange(false)
    }
  }

  useEffect(() => {
    if (defaultExpanded) openRef.current?.()
  }, [defaultExpanded])

  /* ---------------------------- scroll lock ---------------------------- */
  useEffect(() => {
    if (!fixed) return undefined
    document.body.style.overflow = 'hidden'
    document.body.style.touchAction = 'none'
    return () => {
      document.body.style.overflow = ''
      document.body.style.touchAction = ''
    }
  }, [fixed])

  /* ------------------------------ resize ------------------------------- */
  useEffect(() => {
    if (!fixed) return undefined
    const onResize = () => {
      const el = surfaceRef.current
      if (!el) return
      const size = targetSize()
      el.style.setProperty('--map-w', `${size.width}px`)
      el.style.setProperty('--map-h', `${size.height}px`)
      el.style.setProperty('--map-r', `${size.radius}px`)
      setAnchor({
        x: (window.innerWidth - size.width) / 2 - originRef.current.x,
        y: (window.innerHeight - size.height) / 2 - originRef.current.y,
      })
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [fixed])

  /* --------------------- Escape closes the expanded map ---------------- */
  useEffect(() => {
    if (!expanded) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') closeRef.current?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  /* --------------------------- landing demo ---------------------------- */
  useEffect(() => {
    if (!autoDemo || prefersReducedMotion()) return undefined
    let played = false
    try {
      played = sessionStorage.getItem(DEMO_KEY) === '1'
    } catch {
      /* storage unavailable — treat as not played */
    }
    if (played) return undefined
    try {
      sessionStorage.setItem(DEMO_KEY, '1')
    } catch {
      /* storage unavailable — still fine, the timers just run this mount */
    }
    const t1 = window.setTimeout(() => openRef.current?.(), 900)
    const t2 = window.setTimeout(() => closeRef.current?.(), 3400)
    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
    }
  }, [autoDemo])

  /* --------------------------- keyboard/pointer ------------------------ */
  // Pointer toggles only the collapsed circle; while expanded, clicks belong
  // to the map's own controls/info panel — collapse via toolbar or Escape.
  const onActivate = () => {
    if (!expanded) openRef.current?.()
  }
  const onSurfaceKeyDown = (e) => {
    if (expanded) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openRef.current?.()
    }
  }

  const zoomIn = () => setZoom(clampZoom(zoom + 0.25))
  const zoomOut = () => setZoom(clampZoom(zoom - 0.25))
  const zoomReset = () => setZoom(1)

  /* ------------------------------ render ------------------------------- */
  return (
    <div className={`reactive-map reactive-map--${state.condition}${expanded ? ' is-expanded' : ''}`}>
      <MapContainer
        expanded={expanded}
        fixed={fixed}
        showScrim={showScrim}
        surfaceRef={surfaceRef}
        anchor={anchor}
        onActivate={onActivate}
        onKeyDown={onSurfaceKeyDown}
        onTransitionEnd={onSurfaceTransitionEnd}
        onScrimClick={expanded ? () => closeRef.current?.() : null}
      >
        <div className="map-zoom" style={{ '--map-zoom': zoom }}>
          {mapLayer ? mapLayer({ lat, lon }, weather) : <MapCanvas location={location} />}
          <MapWeatherOverlay condition={state.condition} />
          <div className="map-location" style={{ left: markerPos.left, top: markerPos.top }}>
            <MapPulse />
            <MapLocationMarker label={label} />
          </div>
        </div>

        {!expanded ? (
          <div className="map-quick-chip" aria-hidden="true">
            <span className="map-quick-chip__temp">{formatTemperature(weather.temperature_c)}</span>
            <span className="map-quick-chip__cond">{state.icon.label}</span>
          </div>
        ) : null}

        <MapControls
          expanded={expanded}
          zoom={zoom}
          onExpand={() => openRef.current?.()}
          onCollapse={() => closeRef.current?.()}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onZoomReset={zoomReset}
        />

        {expanded ? (
          <WeatherInfoPanel location={location} weather={weather} risk={state.riskTheme} conditionLabel={state.icon.label} />
        ) : null}
      </MapContainer>
    </div>
  )
}
