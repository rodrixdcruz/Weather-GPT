import { t } from '../i18n'

const LEVEL_STYLE = {
  low: { border: 'border-emerald-500/40', bg: 'bg-emerald-500/5', badge: 'bg-emerald-500/15 text-emerald-400' },
  moderate: { border: 'border-yellow-500/40', bg: 'bg-yellow-500/5', badge: 'bg-yellow-500/15 text-yellow-400' },
  high: { border: 'border-orange-500/40', bg: 'bg-orange-500/5', badge: 'bg-orange-500/15 text-orange-400' },
  critical: { border: 'border-red-500/40', bg: 'bg-red-500/5', badge: 'bg-red-500/15 text-red-400' },
}

export default function AlertBanner({ risk, weather, language }) {
  if (!risk) return null
  const style = LEVEL_STYLE[risk.level] || LEVEL_STYLE.low
  const hazardLabel = (risk.hazard_type || 'general_risk').replace('_', ' ')

  return (
    <div id="alertBanner" className={`rounded-xl p-4 flex gap-3.5 items-start border ${style.border} ${style.bg} animate-[fadein_0.4s_ease]`}>
      <span className={`text-[10.5px] font-bold tracking-wide px-2.5 py-1 rounded-md flex-shrink-0 mt-0.5 ${style.badge}`}>
        {risk.level.toUpperCase()}
      </span>
      <div>
        <h3 className="font-display m-0 mb-1 text-[14.5px] capitalize">
          {hazardLabel} {t(language, 'advisory')}
        </h3>
        <p className="m-0 text-[13px] text-slate-100 leading-relaxed">{risk.explanation}</p>
        <div className="flex gap-3.5 mt-2 text-[11.5px] text-slate-300 flex-wrap">
          <span>
            {t(language, 'location')}: <b className="text-slate-100">{weather?.location_label}</b>
          </span>
          <span>
            {t(language, 'source')}: <b className="text-slate-100">{weather?.source}</b>
          </span>
          <span>
            {t(language, 'status')}:{' '}
            <b className="text-slate-100">{weather?.is_verified ? t(language, 'verified') : t(language, 'modelEstimate')}</b>
          </span>
        </div>
      </div>
    </div>
  )
}
