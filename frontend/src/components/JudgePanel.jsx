// Judge demo console — a slide-over panel, reachable ONLY when the session
// belongs to the judge account (session.user.is_judge; the backend gates the
// actual scenario simulation regardless of what this UI offers).
//
// Lets a judge drive the weather simulation through heavy rain, heatwave,
// thunderstorm, flood risk and smog to demonstrate how the WHOLE product
// reacts: risk engine verdicts, safety status, atmosphere, 3D presenter mood,
// emergency automation (walking default, auto-route), chat grounding.
import { t } from '../i18n'

const SCENARIOS = [
  { value: 'normal', icon: '🌍', descKey: 'simNormalDesc' },
  { value: 'heavy_rainfall', icon: '🌧️', descKey: 'simHeavyRainDesc' },
  { value: 'heatwave', icon: '🔥', descKey: 'simHeatwaveDesc' },
  { value: 'thunderstorm', icon: '⛈️', descKey: 'simThunderstormDesc' },
  { value: 'flood_risk', icon: '🌊', descKey: 'simFloodDesc' },
  { value: 'smog', icon: '🌫️', descKey: 'simSmogDesc' },
]

export default function JudgePanel({ open, scenario, onScenarioChange, onClose, language }) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[110] flex justify-end" role="dialog" aria-modal="true" aria-label={t(language, 'judgePanelTitle')}>
      <button
        type="button"
        aria-label={t(language, 'close')}
        onClick={onClose}
        className="absolute inset-0 bg-navy-950/60 border-none p-0 cursor-default"
      />
      <aside className="relative w-full max-w-[360px] h-full bg-navy-900 border-l border-sky/40 shadow-2xl p-5 overflow-y-auto flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="font-display text-[16px] m-0 text-slate-100">🧑‍⚖️ {t(language, 'judgePanelTitle')}</h2>
            <p className="text-[11.5px] text-slate-400 m-0 mt-0.5">{t(language, 'judgePanelSub')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 text-[15px] leading-none px-1"
            aria-label={t(language, 'close')}
          >
            ✕
          </button>
        </div>

        <div className="text-[10.5px] text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-3 py-2 leading-relaxed">
          {t(language, 'simDisclaimer')}
        </div>

        <div className="flex flex-col gap-2">
          {SCENARIOS.map(({ value, icon, descKey }) => {
            const selected = scenario === value
            return (
              <button
                key={value}
                type="button"
                onClick={() => onScenarioChange(value)}
                className={`text-left px-3.5 py-3 rounded-xl border transition ${
                  selected
                    ? 'bg-sky/20 border-sky text-slate-100'
                    : 'bg-navy-800 border-border text-slate-300 hover:border-sky/60'
                }`}
              >
                <span className="flex items-center gap-2 text-[13px] font-semibold">
                  <span aria-hidden="true">{icon}</span>
                  {t(language, `sim_${value}`)}
                  {selected && <span className="ml-auto text-[10px] text-sky font-bold uppercase">{t(language, 'simActive')}</span>}
                </span>
                <span className="block text-[10.5px] text-slate-400 mt-0.5">{t(language, descKey)}</span>
              </button>
            )
          })}
        </div>

        <p className="text-[10.5px] text-slate-500 mt-auto leading-relaxed">{t(language, 'simFooterNote')}</p>
      </aside>
    </div>
  )
}
