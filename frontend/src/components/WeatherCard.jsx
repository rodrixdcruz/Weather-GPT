import { t } from '../i18n'

export default function WeatherCard({ weather, language }) {
  if (!weather) return null
  const observedTime = new Date(weather.observed_at).toLocaleString()
  const hasFeelsLike = weather.apparent_temperature_c != null
  const aqi = weather.air_quality

  return (
    <div className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
          {t(language, 'currentWeather')}
        </span>
        <span
          className={`text-[9.5px] px-2 py-0.5 rounded border ${
            weather.is_verified
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
          }`}
        >
          {weather.is_verified ? t(language, 'verified') : t(language, 'estimate')}
        </span>
      </div>

      <div className="flex items-baseline gap-3 flex-wrap">
        <div className="font-display font-bold text-4xl leading-none">{Math.round(weather.temperature_c)}°C</div>
        {hasFeelsLike && (
          <div className="text-[12px] text-slate-300">
            {t(language, 'feelsLike')} <b className="text-slate-100">{Math.round(weather.apparent_temperature_c)}°C</b>
          </div>
        )}
      </div>
      <div className="text-slate-300 text-xs mt-1">
        {weather.condition} · {weather.location_label}
      </div>
      <div className="text-slate-300 text-[10.5px] mt-0.5">{t(language, 'asOf')} {observedTime}</div>

      <div className="grid grid-cols-2 gap-2 mt-3">
        <Stat label={t(language, 'rainfall')} value={`${weather.rainfall_mm.toFixed(1)} mm`} />
        <Stat label={t(language, 'rainChance')} value={`${weather.precip_probability_pct.toFixed(0)}%`} />
        <Stat label={t(language, 'humidity')} value={`${weather.humidity_pct.toFixed(0)}%`} />
        <Stat
          label={t(language, 'wind')}
          value={`${weather.wind_kph.toFixed(0)} kph${weather.wind_direction ? ` ${weather.wind_direction}` : ''}`}
        />
        {weather.wind_gust_kph != null && (
          <Stat label={t(language, 'windGusts')} value={`${weather.wind_gust_kph.toFixed(0)} kph`} />
        )}
        {aqi && <Stat label={`${t(language, 'aqi')} ${aqi.band ? `· ${aqi.band}` : ''}`} value={aqi.us_aqi.toFixed(0)} />}
      </div>
      {aqi && !aqi.is_verified && (
        <div className="text-[10.5px] text-yellow-400 mt-2">{t(language, 'aqiMockNote')}</div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-navy-700 rounded-lg px-2.5 py-2">
      <div className="font-mono text-sm font-medium">{value}</div>
      <div className="text-[10.5px] text-slate-300 mt-0.5">{label}</div>
    </div>
  )
}
