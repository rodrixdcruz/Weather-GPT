/**
 * Reusable, GPU-friendly ambient effect primitives.
 * Every element animates transform/opacity only, and all layers are
 * position:absolute inside their wrapper (.atmo-fx or .mwo-fx).
 */
const range = (n) => Array.from({ length: n }, (_, i) => i)

export function RainStreaks({ count = 22 }) {
  return (
    <div className="fx-rain" aria-hidden="true">
      {range(count).map((i) => (
        <span
          key={i}
          className="fx-rain-streak"
          style={{
            left: `${(i * 53 + 7) % 96}%`,
            animationDelay: `${(i % 14) * 0.16}s`,
            animationDuration: `${0.7 + (i % 4) * 0.22}s`,
          }}
        />
      ))}
    </div>
  )
}

export function Stars({ count = 34 }) {
  return (
    <div className="fx-stars" aria-hidden="true">
      {range(count).map((i) => (
        <span
          key={i}
          className="fx-star"
          style={{
            left: `${(i * 37 + 11) % 98}%`,
            top: `${(i * 61 + 5) % 55}%`,
            animationDelay: `${(i % 11) * 0.42}s`,
            animationDuration: `${2.4 + (i % 5) * 0.6}s`,
          }}
        />
      ))}
    </div>
  )
}

export function CloudLayer({ variant = 'soft' }) {
  return (
    <div className={`fx-clouds fx-clouds--${variant}`} aria-hidden="true">
      <span className="fx-cloud fx-cloud--a" />
      <span className="fx-cloud fx-cloud--b" />
      <span className="fx-cloud fx-cloud--c" />
    </div>
  )
}

export function WindStreaks({ count = 16 }) {
  return (
    <div className="fx-wind" aria-hidden="true">
      {range(count).map((i) => (
        <span
          key={i}
          className="fx-wind-streak"
          style={{
            top: `${(i * 61 + 9) % 92}%`,
            animationDelay: `${(i % 9) * 0.3}s`,
            animationDuration: `${1.1 + (i % 4) * 0.35}s`,
          }}
        />
      ))}
    </div>
  )
}

export function FrostParticles({ count = 26 }) {
  return (
    <div className="fx-frost" aria-hidden="true">
      {range(count).map((i) => (
        <span
          key={i}
          className="fx-frost-particle"
          style={{
            left: `${(i * 47 + 13) % 98}%`,
            animationDelay: `${(i % 12) * 0.55}s`,
            animationDuration: `${5.5 + (i % 5) * 1.1}s`,
          }}
        />
      ))}
    </div>
  )
}

export function SunGlow({ hot = false }) {
  return <div className={`fx-sun${hot ? ' fx-sun--hot' : ''}`} aria-hidden="true" />
}

export function MoonGlow() {
  return <div className="fx-moon" aria-hidden="true" />
}

export function FogHaze() {
  return <div className="fx-fog" aria-hidden="true" />
}

export function StormFlash() {
  return <div className="fx-storm-flash" aria-hidden="true" />
}

export function HeatWaves() {
  return <div className="fx-heatwave" aria-hidden="true" />
}
