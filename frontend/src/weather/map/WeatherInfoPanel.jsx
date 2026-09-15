import { formatPercent, formatTemperature, formatWindSpeed } from '../ui-state'
import { resolveLocation } from './MapCanvas'

export default function WeatherInfoPanel({ location, weather, risk, conditionLabel }) {
  const { label, lat, lon } = resolveLocation(location)
  const locationText = label || (Number.isFinite(lat) ? `Lat ${lat.toFixed(2)}, Lon ${lon.toFixed(2)}` : 'Location pending')

  return (
    <aside className="map-info-panel" aria-live="polite">
      <header className="map-info-panel__head">
        <span className="map-info-panel__location">{locationText}</span>
        {weather.is_verified ? <span className="map-info-panel__verified">✓ Verified</span> : null}
      </header>

      <div className="map-info-panel__temp">
        {formatTemperature(weather.temperature_c)}
        <small>{conditionLabel}</small>
      </div>

      <dl className="map-info-panel__stats">
        <div><dt>Feels like</dt><dd>{formatTemperature(weather.apparent_temperature_c)}</dd></div>
        <div><dt>Humidity</dt><dd>{formatPercent(weather.humidity_pct)}</dd></div>
        <div><dt>Wind</dt><dd>{formatWindSpeed(weather.wind_kph)}</dd></div>
        <div><dt>Rain prob.</dt><dd>{formatPercent(weather.precip_probability_pct)}</dd></div>
      </dl>

      <div className="map-info-panel__risk">
        <span className={`map-risk-dot map-risk-dot--${risk.tone}`} aria-hidden="true" />
        <strong>{risk.label.toUpperCase()} RISK</strong>
        <span>· {risk.hazard}</span>
      </div>
      <p className="map-info-panel__action">{risk.action}</p>

      <footer className="map-info-panel__foot">Source: {weather.source || 'WeatherGPT API'}</footer>
    </aside>
  )
}
