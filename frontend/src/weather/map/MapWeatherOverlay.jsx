import { CloudLayer, FogHaze, FrostParticles, HeatWaves, RainStreaks, StormFlash, SunGlow, WindStreaks } from '../effects'

export default function MapWeatherOverlay({ condition }) {
  const t = (cls) => <div key={cls} className={`mwo-tint ${cls}`} aria-hidden="true" />
  let fx

  switch (condition) {
    case 'sunny':
      fx = [t('mwo-tint--sunny')]
      break
    case 'partly-cloudy':
      fx = [t('mwo-tint--cloudy'), <CloudLayer key="clouds" />]
      break
    case 'cloudy':
      fx = [t('mwo-tint--cloudy'), <CloudLayer key="clouds" variant="storm" />]
      break
    case 'rain':
      fx = [t('mwo-tint--rain'), <RainStreaks key="rain" count={16} />]
      break
    case 'heavy-rain':
      fx = [t('mwo-tint--rain'), <RainStreaks key="rain" count={24} />]
      break
    case 'storm':
      fx = [t('mwo-tint--storm'), <CloudLayer key="clouds" variant="storm" />, <RainStreaks key="rain" count={24} />, <StormFlash key="flash" />]
      break
    case 'extreme-heat':
      fx = [t('mwo-tint--heat'), <SunGlow key="sun" hot />, <HeatWaves key="waves" />]
      break
    case 'strong-wind':
      fx = [t('mwo-tint--wind'), <WindStreaks key="wind" />]
      break
    case 'cold':
      fx = [t('mwo-tint--cold'), <FrostParticles key="frost" />]
      break
    case 'fog':
      fx = [t('mwo-tint--fog'), <FogHaze key="fog" />]
      break
    default:
      fx = []
  }

  return (
    <div className="map-weather-overlay" aria-hidden="true">
      <div className="mwo-fx">{fx}</div>
      <div className="mwo-vignette" />
    </div>
  )
}
