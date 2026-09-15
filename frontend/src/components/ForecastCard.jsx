// Multi-day forecast. Responsive: horizontal scroll on mobile, grid on
// larger screens. No heavy animation — a subtle hover lift only.
import { t } from '../i18n'
import { EmptyState, ErrorState, LoadingState } from './StateViews'

// Minimal WMO-code glyphs shared across cards.
const CONDITION_ICON = (code) => {
  if (code == null) return '🌡️'
  if (code === 0) return '☀️'
  if (code === 1 || code === 2) return '⛅'
  if (code === 3) return '☁️'
  if (code === 45 || code === 48) return '🌫️'
  if (code >= 51 && code <= 67) return '🌧️'
  if (code >= 71 && code <= 86) return '🌨️'
  if (code >= 95) return '⛈️'
  return '🌡️'
}

function dayLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00`)
  if (Number.isNaN(date.getTime())) return dateStr // mock provider uses "day1" etc.
  return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

export default function ForecastCard({ forecast, loading, error, language = 'en', onRetry }) {
  return (
    <section aria-label={t(language, 'forecast')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display m-0 text-[14.5px]">{t(language, 'forecast')}</h3>
        <span className="text-[10.5px] text-slate-300">{forecast?.length ? `${forecast.length} ${t(language, 'days')}` : ''}</span>
      </div>

      {loading ? (
        <LoadingState language={language} height="h-32" label={t(language, 'loadingForecast')} />
      ) : error ? (
        <ErrorState language={language} message={error} onRetry={onRetry} height="h-32" />
      ) : !forecast?.length ? (
        <EmptyState language={language} message={t(language, 'noForecast')} height="h-32" />
      ) : (
        <ol className="list-none m-0 p-0 flex gap-2 overflow-x-auto lg:grid lg:grid-cols-5 lg:overflow-visible pb-1">
          {forecast.map((day) => (
            <li
              key={day.date}
              className="flex-shrink-0 w-[130px] lg:w-auto bg-navy-700/60 border border-border rounded-xl p-3 flex flex-col items-center gap-1.5 text-center hover:border-sky/50 transition"
            >
              <span className="text-[11px] text-slate-300 font-semibold">{dayLabel(day.date)}</span>
              <span aria-hidden="true" className="text-xl">{CONDITION_ICON(day.weather_code)}</span>
              <span className="text-[11.5px] leading-tight min-h-[14px]">{day.condition || ''}</span>
              <span className="font-display font-bold text-lg leading-none">{Math.round(day.temperature_c)}°C</span>
              <span className="text-[10.5px] text-slate-300">
                💧 {day.rainfall_mm?.toFixed(1)} mm
              </span>
              {day.precipitation_probability_pct != null && (
                <span className="text-[10.5px] text-slate-300">
                  {t(language, 'rainChance')}: {Math.round(day.precipitation_probability_pct)}%
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
