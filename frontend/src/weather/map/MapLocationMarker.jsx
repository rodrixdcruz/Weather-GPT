/* Custom teardrop pin + white core + live location label. */
import MapPulse from './MapPulse'

export default function MapLocationMarker({ label }) {
  const readable = label && label.trim() ? label : 'Current location'
  return (
    <div className="map-location-marker" role="img" aria-label={`Location marker: ${readable}`}>
      <span className="map-pin" aria-hidden="true" />
      <span className="map-marker-label">{readable}</span>
    </div>
  )
}
