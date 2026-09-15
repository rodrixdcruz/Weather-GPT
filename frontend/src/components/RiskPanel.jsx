// Risk section: renders the role-aware assessment from GET /api/v1/risk.
// Severity is never conveyed by color alone — every badge also carries a
// distinct icon and text label. Language stays plain and actionable.
import { t } from '../i18n'
import { EmptyState } from './StateViews'

// style: badge text/bg, bar color, and a non-color icon per severity.
const SEVERITY_STYLE = {
  low: { badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', bar: 'bg-emerald-500', icon: '✅', weight: 'font-medium' },
  moderate: { badge: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30', bar: 'bg-yellow-500', icon: '△', weight: 'font-semibold' },
  high: { badge: 'bg-orange-500/15 text-orange-400 border-orange-500/30', bar: 'bg-orange-500', icon: '▲', weight: 'font-semibold' },
  extreme: { badge: 'bg-red-500/15 text-red-400 border-red-500/30', bar: 'bg-red-500', icon: '⬤', weight: 'font-bold' },
}

export function SeverityBadge({ severity, language = 'en' }) {
  const style = SEVERITY_STYLE[severity] || SEVERITY_STYLE.low
  return (
    <span className={`inline-flex items-center gap-1 text-[10.5px] tracking-wide px-2 py-0.5 rounded border ${style.badge} ${style.weight}`}>
      <span aria-hidden="true">{style.icon}</span>
      {t(language, `severity_${severity}`)}
    </span>
  )
}

export function RiskCard({ risk }) {
  return (
    <li className="bg-navy-700/60 border border-border rounded-xl p-3.5 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <h4 className="font-display text-[14px] m-0">{risk.title}</h4>
        <SeverityBadge severity={risk.severity} />
      </div>

      <div className="h-1.5 rounded-full bg-navy-950/60 overflow-hidden" aria-hidden="true">
        <div className={`h-full ${SEVERITY_STYLE[risk.severity]?.bar || 'bg-emerald-500'}`} style={{ width: `${Math.min(100, Math.max(0, risk.score))}%` }} />
      </div>

      <p className="m-0 text-[12.5px] text-slate-100 leading-relaxed">{risk.explanation}</p>

      <div className="flex flex-wrap gap-1.5 text-[10.5px] text-slate-300">
        {risk.affected_day && (
          <span className="bg-navy-800 border border-border rounded px-2 py-0.5">
            {t('en', 'affectsDay')}: <b className="text-slate-100">{risk.affected_day}</b>
          </span>
        )}
        {risk.affected_metric && risk.measured_value != null && (
          <span className="bg-navy-800 border border-border rounded px-2 py-0.5">
            <b className="text-slate-100">{risk.affected_metric.replace(/_/g, ' ')}: {risk.measured_value}</b>
          </span>
        )}
        <span className="bg-navy-800 border border-border rounded px-2 py-0.5">
          {t('en', 'riskScore')}: <b className="text-slate-100">{Math.round(risk.score)}/100</b>
        </span>
      </div>

      {risk.guidance?.map((line, i) => (
        <p key={i} className="m-0 text-[12.5px] leading-relaxed flex gap-2">
          <span aria-hidden="true" className="text-sky flex-shrink-0">→</span>
          <span>{line}</span>
        </p>
      ))}
    </li>
  )
}

export default function RiskPanel({ assessment, loading, error, language = 'en', onRetry }) {
  if (loading) {
    return (
      <section aria-busy="true" className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
        <h3 className="font-display m-0 mb-1 text-[14.5px]">{t(language, 'riskAssessment')}</h3>
        <div className="h-40" />
      </section>
    )
  }

  return (
    <section aria-label={t(language, 'riskAssessment')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
        <h3 className="font-display m-0 text-[14.5px]">{t(language, 'riskAssessment')}</h3>
        {assessment && (
          <div className="flex items-center gap-2">
            <span className="text-[10.5px] text-slate-300">{t(language, 'roleLabel')}:</span>
            <span className="text-[10.5px] font-semibold text-sky">{t(language, `role_${assessment.role}`)}</span>
          </div>
        )}
      </div>

      {error ? (
        <div role="alert" className="rounded-xl p-4 border border-red-500/40 bg-red-500/5 text-sm flex flex-col gap-2">
          <span>{t(language, 'riskLoadFailed')}</span>
          {onRetry && (
            <button type="button" onClick={onRetry} className="self-start px-3 py-1.5 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition">
              {t(language, 'retry')}
            </button>
          )}
        </div>
      ) : !assessment ? (
        <EmptyState language={language} message={t(language, 'riskUnavailable')} />
      ) : assessment.risks.length === 0 ? (
        <EmptyState language={language} message={t(language, 'noRisks')} />
      ) : (
        <ul className="list-none m-0 p-0 flex flex-col gap-2.5">
          {assessment.risks.map((risk, i) => (
            <RiskCard key={`${risk.category}-${risk.affected_day || 'now'}-${i}`} risk={risk} />
          ))}
        </ul>
      )}
    </section>
  )
}
