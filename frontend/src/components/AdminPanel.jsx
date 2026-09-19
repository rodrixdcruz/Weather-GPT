// Admin panel (admin accounts only).
//
// MausamBagha AI's intelligence is a MODEL STACK, so this panel is built around
// model observability rather than generic server stats: which tiers exist and
// are actually reachable, what the model has been doing since the backend
// started (requests, which tier served them, fallback rate, latency), what
// grounds it (RAG knowledge + risk engine), and who is signed in with which
// locked role.
//
// The backend enforces access — this component only decides what to render.
import { useCallback, useEffect, useState } from 'react'
import { t } from '../i18n'
import { api } from '../lib/api'

const REFRESH_MS = 15000

function Section({ title, hint, children }) {
  return (
    <section className="bg-navy-900/60 border border-border rounded-2xl p-4">
      <h3 className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold m-0">{title}</h3>
      {hint && <p className="text-[11px] text-slate-400 m-0 mt-1">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

function Metric({ label, value, tone = 'normal' }) {
  const toneClass =
    tone === 'warn' ? 'text-yellow-300' : tone === 'bad' ? 'text-red-300' : tone === 'good' ? 'text-emerald-300' : 'text-slate-100'
  return (
    <div className="bg-navy-800 border border-border rounded-xl px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">{label}</div>
      <div className={`text-[15px] font-semibold ${toneClass}`}>{value}</div>
    </div>
  )
}

function TierCard({ tier, language }) {
  const ok = tier.configured
  return (
    <div className="bg-navy-800 border border-border rounded-xl p-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-[12.5px] font-semibold text-slate-100">{tier.name}</span>
        <span className="flex items-center gap-1.5">
          {tier.free && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border text-sky border-sky/50 bg-sky/10">
              {t(language, 'adminTierFree')}
            </span>
          )}
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
              ok ? 'text-emerald-300 border-emerald-500/50 bg-emerald-500/10' : 'text-yellow-300 border-yellow-500/50 bg-yellow-500/10'
            }`}
          >
            {ok ? t(language, 'adminTierReachable') : t(language, 'adminTierDown')}
          </span>
        </span>
      </div>
      <div className="text-[11px] text-slate-400 mt-1">
        {t(language, 'adminTierModel')}: <span className="text-slate-300">{tier.model}</span>
      </div>
      {tier.requires_key === false && (
        <div className="text-[10.5px] text-emerald-300 mt-0.5">{t(language, 'adminTierKeyless')}</div>
      )}
      {tier.limits && (
        <div className="text-[10.5px] text-slate-400 mt-0.5">
          {t(language, 'adminTierLimits')}: <span className="text-slate-300">{tier.limits}</span>
        </div>
      )}
      <p className="text-[11px] text-slate-300 m-0 mt-1.5">{tier.detail}</p>
      {tier.members?.length > 1 && (
        <div className="mt-2 border-t border-border pt-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">
            {t(language, 'adminTierChain')}
          </div>
          <ol className="m-0 pl-4 flex flex-col gap-0.5">
            {tier.members.map((m) => (
              <li key={m.preset || m.name} className="text-[11px] text-slate-300">
                <span className="font-semibold">{m.name}</span>
                <span className="text-slate-500"> · {m.model}</span>
                {m.free && <span className="text-sky"> · {t(language, 'adminTierFree')}</span>}
                {m.cooling && (
                  <span className="text-yellow-300"> · {t(language, 'adminTierCooling')}</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {tier.base_url && (
        <div className="text-[10px] text-slate-500 mt-1 break-all font-mono">{tier.base_url}</div>
      )}
      {!ok && tier.signup_url && (
        <a
          className="text-[10.5px] text-sky underline mt-1 inline-block"
          href={tier.signup_url}
          target="_blank"
          rel="noreferrer"
        >
          {t(language, 'adminTierGetKey')} →
        </a>
      )}
    </div>
  )
}

const LOCALES = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }

function fmtTime(value, language) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(LOCALES[language] || undefined)
  } catch {
    return String(value)
  }
}

export default function AdminPanel({ language, onClose, session }) {
  const [data, setData] = useState(null)
  const [sessions, setSessions] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [overview, active] = await Promise.all([api.getAdminOverview(), api.getAdminSessions()])
      setData(overview)
      setSessions(active)
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err?.status === 403 ? t(language, 'adminAdminOnly') : err?.message || t(language, 'adminError'))
    } finally {
      setLoading(false)
    }
  }, [language])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const model = data?.model
  const metrics = model?.metrics
  const det = data?.deterministic_layer

  return (
    <div className="fixed inset-0 z-[60] bg-navy-950/80 backdrop-blur-sm overflow-y-auto p-4">
      <div className="max-w-[1100px] mx-auto bg-navy-950 border border-border rounded-2xl">
        {/* Header */}
        <header className="flex items-start justify-between gap-3 p-4 border-b border-border flex-wrap sticky top-0 bg-navy-950/95 backdrop-blur z-10 rounded-t-2xl">
          <div>
            <h2 className="font-display font-bold text-[17px] m-0">🛠️ {t(language, 'adminTitle')}</h2>
            <p className="text-slate-300 text-[11.5px] m-0 mt-0.5">{t(language, 'adminSubtitle')}</p>
            <p className="text-slate-400 text-[10.5px] m-0 mt-1">
              {t(language, 'signedInAs')}: <span className="text-slate-300">{session?.user?.display_name || session?.user?.username}</span>
              {refreshedAt ? ` · ${t(language, 'lastUpdated')} ${fmtTime(refreshedAt, language)}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              className="px-3.5 py-1.5 rounded-full text-xs bg-navy-800 border border-border hover:border-sky transition"
            >
              ⟳ {t(language, 'adminRefresh')}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-full text-xs bg-navy-800 border border-border hover:border-sky transition"
            >
              {t(language, 'close')}
            </button>
          </div>
        </header>

        <div className="p-4 flex flex-col gap-4">
          {loading && <div className="text-slate-300 text-[12.5px]">{t(language, 'adminLoading')}</div>}
          {error && (
            <div role="alert" className="text-[12px] text-red-300 bg-red-500/10 border border-red-500/40 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {data && (
            <>
              {data.notes?.length > 0 && (
                <Section title={t(language, 'adminNotes')}>
                  <ul className="m-0 pl-4 text-[11.5px] text-yellow-300 flex flex-col gap-1">
                    {data.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* --- The ML model itself --- */}
              <Section title={t(language, 'adminModelSection')} hint={t(language, 'adminModelHint')}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                  <Metric label={t(language, 'adminProviderMode')} value={model.provider_mode} />
                  <Metric label={t(language, 'adminRequests')} value={metrics.requests} />
                  <Metric
                    label={t(language, 'adminFallbackRate')}
                    value={`${metrics.fallback_rate_pct}%`}
                    tone={metrics.fallback_rate_pct > 50 ? 'warn' : metrics.requests ? 'good' : 'normal'}
                  />
                  <Metric
                    label={t(language, 'adminLatencyAvg')}
                    value={metrics.latency_avg_ms == null ? '—' : `${metrics.latency_avg_ms} ms`}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {model.tiers.map((tier) => (
                    <TierCard key={tier.name} tier={tier} language={language} />
                  ))}
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
                  <Metric label={t(language, 'adminFallbacks')} value={metrics.fallbacks} />
                  <Metric label={t(language, 'adminLatencyP95')} value={metrics.latency_p95_ms == null ? '—' : `${metrics.latency_p95_ms} ms`} />
                  <Metric label={t(language, 'adminServedBy')} value={metrics.served_mostly_by || '—'} />
                  <Metric label={t(language, 'adminLatencySamples')} value={metrics.latency_samples} />
                </div>

                {metrics.requests === 0 && (
                  <p className="text-[11px] text-slate-400 m-0 mt-2">{t(language, 'adminNoRequests')}</p>
                )}
                {Object.keys(metrics.by_provider || {}).length > 0 && (
                  <div className="mt-3">
                    <div className="text-[10.5px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">
                      {t(language, 'adminByProvider')}
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {Object.entries(metrics.by_provider).map(([name, count]) => {
                        const pct = metrics.requests ? Math.round((count / metrics.requests) * 100) : 0
                        return (
                          <div key={name} className="flex items-center gap-2">
                            <span className="text-[11px] text-slate-300 w-24 shrink-0">{name}</span>
                            <span className="flex-1 h-2 rounded-full bg-navy-800 overflow-hidden">
                              <span className="block h-full bg-sky" style={{ width: `${pct}%` }} />
                            </span>
                            <span className="text-[10.5px] text-slate-400 w-14 text-right">
                              {count} · {pct}%
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                {metrics.last_error && (
                  <p className="text-[11px] text-yellow-300 m-0 mt-3 break-words">
                    {t(language, 'adminLastError')}: {metrics.last_error_kind ? `[${metrics.last_error_kind}] ` : ''}
                    {metrics.last_error}
                  </p>
                )}
              </Section>

              {/* --- What grounds the model --- */}
              <Section title={t(language, 'adminRag')} hint={t(language, 'adminRagHint')}>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <Metric label={t(language, 'adminRagEnabled')} value={model.rag.enabled ? '✓' : '✗'} tone={model.rag.enabled ? 'good' : 'warn'} />
                  <Metric label={t(language, 'adminRagTopK')} value={model.rag.top_k} />
                  <Metric label={t(language, 'adminRagSource')} value={model.rag.source} />
                </div>
              </Section>

              <Section title={t(language, 'adminDeterministic')} hint={t(language, 'adminDeterministicHint')}>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
                  <Metric label={t(language, 'adminRiskProfile')} value={det.risk_engine.profile} />
                  <Metric label={t(language, 'adminSeverities')} value={(det.risk_engine.severities || []).join(' · ') || '—'} />
                  <Metric
                    label={t(language, 'adminGuidance')}
                    value={det.risk_engine.guidance_templates ?? '—'}
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
                  <Metric label={t(language, 'adminWeatherProvider')} value={det.data_sources.weather_provider} />
                  <Metric
                    label={t(language, 'adminAirQuality')}
                    value={det.data_sources.air_quality_enabled ? '✓' : '✗'}
                    tone={det.data_sources.air_quality_enabled ? 'good' : 'warn'}
                  />
                  <Metric label={t(language, 'adminAlertProvider')} value={det.safety_alert_provider} />
                </div>
                {det.risk_engine.thresholds && (
                  <div className="bg-navy-800 border border-border rounded-xl p-3">
                    <div className="text-[10.5px] uppercase tracking-wide text-slate-400 font-semibold mb-1.5">
                      {t(language, 'adminThresholds')}
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
                      {Object.entries(det.risk_engine.thresholds).map(([key, val]) => (
                        <div key={key} className="flex items-center justify-between gap-2 text-[11px]">
                          <span className="text-slate-400">{key}</span>
                          <span className="text-slate-200 font-mono">
                            {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Section>

              {/* --- Service + database --- */}
              <Section title={t(language, 'adminSystem')}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Metric label={t(language, 'adminVersion')} value={`${data.app.name} ${data.app.version}`} />
                  <Metric label={t(language, 'adminEnv')} value={data.app.env} />
                  <Metric label={t(language, 'adminUptime')} value={`${Math.floor(data.app.uptime_seconds / 60)} min`} />
                  <Metric label={t(language, 'adminPython')} value={data.app.python} />
                  <Metric label={t(language, 'adminRuntime')} value={data.app.platform} />
                  <Metric label={t(language, 'adminAccounts')} value={data.database.accounts} />
                  <Metric
                    label={t(language, 'adminDatabase')}
                    value={data.database.reachable ? t(language, 'adminDbReachable') : t(language, 'adminDbUnreachable')}
                    tone={data.database.reachable ? 'good' : 'bad'}
                  />
                  <Metric label={t(language, 'adminSessionTtl')} value={`${data.auth.session_ttl_hours} h`} />
                </div>
              </Section>

              {/* --- Sessions: each carries its own locked role --- */}
              <Section title={t(language, 'adminSessions')} hint={t(language, 'adminSessionsHint')}>
                {!sessions || sessions.count === 0 ? (
                  <p className="text-[11.5px] text-slate-400 m-0">{t(language, 'adminNoSessions')}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-[11.5px]">
                      <thead>
                        <tr className="text-left text-slate-400 text-[10.5px] uppercase tracking-wide">
                          <th className="py-1.5 pr-3 font-semibold">{t(language, 'adminColUser')}</th>
                          <th className="py-1.5 pr-3 font-semibold">{t(language, 'adminColRole')}</th>
                          <th className="py-1.5 pr-3 font-semibold">{t(language, 'adminColCreated')}</th>
                          <th className="py-1.5 font-semibold">{t(language, 'adminColExpires')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sessions.sessions.map((row) => (
                          <tr key={`${row.username}-${row.created_at}`} className="border-t border-border">
                            <td className="py-2 pr-3 text-slate-200">
                              {row.display_name}
                              {row.is_admin && (
                                <span className="ml-2 text-[9.5px] font-bold px-1.5 py-0.5 rounded-full bg-sky/20 border border-sky text-sky">
                                  ADMIN
                                </span>
                              )}
                            </td>
                            <td className="py-2 pr-3 text-slate-300">
                              {t(language, `role_${row.session_role}`)}
                              <span className="ml-2 text-[9.5px] text-slate-500">
                                🔒 {t(language, 'adminLockedBadge')}
                              </span>
                            </td>
                            <td className="py-2 pr-3 text-slate-400">{fmtTime(row.created_at, language)}</td>
                            <td className="py-2 text-slate-400">{fmtTime(row.expires_at, language)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
