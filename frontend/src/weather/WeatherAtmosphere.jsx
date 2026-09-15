import { CloudLayer, FogHaze, FrostParticles, HeatWaves, MoonGlow, RainStreaks, Stars, StormFlash, SunGlow, WindStreaks } from './effects'
import { PRIORITY } from './ui-state'
import './weather-scape.css'

function atmosphereFx(animation) {
  if (animation === 'sunlight') return <SunGlow />
  if (animation === 'starry-night') {
    return (
      <div className="atmo-fx" aria-hidden="true">
        <MoonGlow />
        <Stars />
      </div>
    )
  }
  if (animation === 'clouds') return <div className="atmo-fx"><CloudLayer /></div>
  if (animation === 'rain') return <div className="atmo-fx"><RainStreaks /></div>
  if (animation === 'storm') {
    return (
      <div className="atmo-fx">
        <CloudLayer variant="storm" />
        <RainStreaks count={30} />
        <StormFlash />
      </div>
    )
  }
  if (animation === 'heat') return <div className="atmo-fx"><SunGlow hot /><HeatWaves /></div>
  if (animation === 'wind') return <div className="atmo-fx"><WindStreaks /></div>
  if (animation === 'frost') return <div className="atmo-fx"><FrostParticles /><FogHaze /></div>
  if (animation === 'fog') return <div className="atmo-fx"><FogHaze /></div>
  return null
}

/**
 * Page-level reactive environment. Wrap the existing dashboard — it changes
 * only the background sky, time-of-day glow and ambient FX; all content and
 * functionality stay untouched.
 */
export default function WeatherAtmosphere({ state, children, className = '' }) {
  const glow = state.theme.timeOverlay
  const safety = state.priority === PRIORITY.SAFETY_FIRST
  return (
    <div
      className={`weather-atmosphere atmosphere--${state.condition} ${state.theme.isNight ? 'is-night' : ''} ${safety ? 'is-safety' : ''} ${className}`}
      style={{ '--atmo-bg': state.background, '--atmo-accent': state.theme.accent }}
    >
      <div className="atmo-sky" aria-hidden="true" />
      {glow ? <div className="atmo-timeglow" style={{ background: glow }} aria-hidden="true" /> : null}
      {atmosphereFx(state.animation)}
      <div className="atmo-content">{children}</div>
    </div>
  )
}
