import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { t } from '../i18n'
import { ErrorState, LoadingState } from './StateViews'
import { SeverityBadge } from './RiskPanel'

// WeatherGPT's own escalation ladder. NOT official government warning
// levels — the disclaimer below says so explicitly.
const STATUS_STYLE = {
  normal: { border: 'border-emerald-500/40', bg: 'bg-emerald-500/5', text: 'text-emerald-400', icon: '✅' },
  watch: { border: 'border-yellow-500/40', bg: 'bg-yellow-500/5', text: 'text-yellow-400', icon: '👀' },
  warning: { border: 'border-orange-500/40', bg: 'bg-orange-500/5', text: 'text-orange-400', icon: '⚠️' },
  critical: { border: 'border-red-500/40', bg: 'bg-red-500/5', text: 'text-red-400', icon: '🚨' },
}

// Curated, configurable emergency information. No invented numbers:
// 112 is India's national emergency helpline; everything else is a
// pointer to official portals, not fabricated local contacts.
const EMERGENCY_INFO = [
  { label: 'National Emergency Helpline (India)', value: '112' },
  { label: 'Official warnings', value: 'imd.gov.in · ndma.gov.in' },
]

export default function SafetyDashboard({ location, role, scenario, language = 'en', onUseDashboardLocation }) {
  const [safety, setSafety] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .getSafety(location.latitude, location.longitude, role, scenario)
      .then((res) => {
        if (!cancelled) setSafety(res)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [location, role, scenario])

  if (loading) {
    return (
      <section aria-busy="true" className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
        <LoadingState language={language} height="h-56" label={t(language, 'loadingSafety')} />
      </section>
    )
  }

  if (error) {
    return (
      <section className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
        <ErrorState language={language} message={error} onRetry={onUseDashboardLocation} height="h-48" />
      </section>
    )
  }

  const style = STATUS_STYLE[safety.status] || STATUS_STYLE.normal
  const updated = new Date(safety.generated_at).toLocaleString()

  return (
    <div className="flex flex-col gap-4">
      {/* Overall status */}
      <section aria-label={t(language, 'safetyStatus')} className={`rounded-2xl border p-4 ${style.border} ${style.bg}`}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <span aria-hidden="true" className="text-3xl">{style.icon}</span>
            <div>
              <div className={`font-display font-bold text-lg ${style.text}`}>{t(language, `safety_${safety.status}`)}</div>
              <div className="text-[11px] text-slate-300 uppercase tracking-wide">{t(language, 'safetyStatusLabel')}</div>
            </div>
          </div>
          <div className="text-right text-[11px] text-slate-300">
            <div>{safety.condition} · {Math.round(safety.temperature_c)}°C</div>
            <div>{safety.latitude.toFixed(3)}, {safety.longitude.toFixed(3)}</div>
            <div>{t(language, 'lastUpdated')}: {updated}</div>
          </div>
        </div>
        <p className="m-0 mt-3 text-[11px] text-slate-300 leading-relaxed border-t border-border pt-2">{safety.disclaimer}</p>
      </section>

      {/* Active alerts */}
      <section aria-label={t(language, 'activeAlerts')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
        <h3 className="font-display m-0 mb-3 text-[14.5px]">{t(language, 'activeAlerts')} ({safety.alerts.length})</h3>
        {safety.alerts.length === 0 ? (
          <p className="m-0 text-[13px] text-slate-100">✅ {t(language, 'noActiveAlerts')}</p>
        ) : (
          <ul className="list-none m-0 p-0 flex flex-col gap-2.5">
            {safety.alerts.map((alert) => (
              <li key={alert.id} className="bg-navy-700/60 border border-border rounded-xl p-3.5 flex flex-col gap-2">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <h4 className="font-display m-0 text-[14px]">{alert.title}</h4>
                  <SeverityBadge severity={alert.severity} language={language} />
                </div>
                <p className="m-0 text-[12.5px] text-slate-100 leading-relaxed">{alert.explanation}</p>
                <p className="m-0 text-[12.5px] leading-relaxed flex gap-2">
                  <span aria-hidden="true" className="text-sky flex-shrink-0">→</span>
                  <span>{alert.recommended_action}</span>
                </p>
                <span className="text-[10px] text-slate-300">
                  {t(language, 'alertSource')}: {alert.source} · {t(language, 'weathergptGenerated')}
                </span>
              </li>
            ))}
          </ul>
        )}
        {safety.official_alerts.length > 0 && (
          <div className="mt-3 border-t border-border pt-3">
            <h4 className="m-0 mb-2 text-[13px] font-semibold">🏛️ {t(language, 'officialAlerts')}</h4>
            <ul className="list-none m-0 p-0 flex flex-col gap-2">
              {safety.official_alerts.map((alert) => (
                <li key={alert.id} className="bg-navy-700/60 border border-sky/40 rounded-xl p-3 text-[12.5px]">
                  <b>{alert.title}</b> — {alert.explanation}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Checklist */}
        <section aria-label={t(language, 'safetyChecklist')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
          <h3 className="font-display m-0 mb-3 text-[14.5px]">{t(language, 'safetyChecklist')}</h3>
          <ul className="list-none m-0 p-0 flex flex-col gap-2">
            {safety.checklist.map((item, i) => (
              <li key={`${item.category}-${i}`} className="flex gap-2.5 text-[13px] leading-relaxed items-start">
                <input type="checkbox" id={`chk-${i}`} className="mt-1 accent-sky" />
                <label htmlFor={`chk-${i}`} className="cursor-pointer">
                  {item.text}
                  <span className="block text-[10px] text-slate-300 uppercase tracking-wide">{item.category.replace(/_/g, ' ')}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>

        {/* Emergency information */}
        <section aria-label={t(language, 'emergencyInfo')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
          <h3 className="font-display m-0 mb-3 text-[14.5px]">🆘 {t(language, 'emergencyInfo')}</h3>
          <ul className="list-none m-0 p-0 flex flex-col gap-2">
            {EMERGENCY_INFO.map((info) => (
              <li key={info.label} className="bg-navy-700 rounded-lg px-3 py-2 flex justify-between gap-2 text-[12.5px] flex-wrap">
                <span className="text-slate-300">{info.label}</span>
                <b className="font-mono">{info.value}</b>
              </li>
            ))}
          </ul>
          <p className="m-0 mt-3 text-[11px] text-slate-300 leading-relaxed">
            {t(language, 'emergencyNote')}
          </p>
        </section>
      </div>
    </div>
  )
}
