import { t } from '../i18n'

const SCENARIOS = [
  { value: 'normal', label: 'Normal' },
  { value: 'heavy_rainfall', label: 'Heavy Rainfall' },
  { value: 'heatwave', label: 'Heatwave' },
  { value: 'thunderstorm', label: 'Thunderstorm' },
  { value: 'flood_risk', label: 'Flood Risk' },
  { value: 'smog', label: 'Smog (Poor AQI)' },
]

export default function TopBar({ scenario, onScenarioChange, langLabel, onLangClick, onSosClick, language, weather = null }) {
  return (
    <>
      <div className="flex items-center justify-between gap-2.5 px-5 py-3.5 border-b border-border bg-navy-950/70 backdrop-blur sticky top-0 z-50 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8.5 h-8.5 w-[34px] h-[34px] rounded-[9px] bg-gradient-to-br from-sky to-[#1c5fb0] flex items-center justify-center font-bold text-white text-sm">
            WG
          </div>
          <div>
            <h1 className="font-display font-bold text-[17px] m-0">WeatherGPT</h1>
            <small className="block text-slate-300 text-[10.5px] uppercase tracking-wide">
              {t(language, 'brandSub')}
            </small>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <select
            className="bg-navy-800 border border-border text-slate-100 px-3 py-1.5 rounded-full text-xs cursor-pointer"
            value={scenario}
            onChange={(e) => onScenarioChange(e.target.value)}
          >
            {SCENARIOS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>

          <button
            className="bg-navy-800 border border-border text-slate-100 px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 hover:border-sky transition"
            onClick={onLangClick}
          >
            🌐 {langLabel}
          </button>

          <button
            className="bg-gradient-to-br from-red-500 to-red-700 border-none text-white font-bold tracking-wide px-4 py-2 rounded-full text-xs animate-sos"
            onClick={onSosClick}
          >
            {t(language, 'sos')}
          </button>
        </div>
      </div>

      {/* Data-source banner: reflects the ACTUAL source of the data being
          shown. Live = verified provider readings (e.g. Open-Meteo);
          demo = mock fixtures or unknown/loading — never the reverse. */}
      {weather?.is_verified ? (
        <div className="bg-[repeating-linear-gradient(135deg,#0a2f1c,#0a2f1c_10px,#0c3320_10px,#0c3320_20px)] border-b border-[#1d6b43] text-[#9ff0c6] text-xs px-5 py-2 flex items-center gap-2.5 flex-wrap justify-between">
          <span>✓ {t(language, 'liveBanner')}</span>
        </div>
      ) : (
        <div className="bg-[repeating-linear-gradient(135deg,#3a2f0a,#3a2f0a_10px,#33290a_10px,#33290a_20px)] border-b border-[#6b5210] text-[#ffd873] text-xs px-5 py-2 flex items-center gap-2.5 flex-wrap justify-between">
          <span>⚠ {t(language, 'demoBanner')}</span>
        </div>
      )}
    </>
  )
}
