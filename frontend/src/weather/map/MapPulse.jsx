/* Reusable pulsing ring — the "locationPulse" concept. */
export default function MapPulse({ rings = 3, delay = 0, className = '' }) {
  const items = []
  for (let i = 0; i < rings; i += 1) {
    items.push(
      <span
        key={i}
        className="map-pulse-ring"
        style={{ animationDelay: `${delay + i * 0.75}s` }}
      />,
    )
  }
  return <div className={`map-pulse ${className}`} aria-hidden="true">{items}</div>
}
