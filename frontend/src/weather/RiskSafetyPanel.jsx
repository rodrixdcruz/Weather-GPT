/**
 * Risk-aware UI panel. Never communicates risk through color alone — the
 * level, hazard type, score, explanation and recommended action are always
 * text. HIGH / EXTREME switch the panel into safety-first styling.
 */
const TONES = {
  neutral: { cls: 'risk-panel--neutral', badge: 'LOW RISK' },
  safe: { cls: 'risk-panel--safe', badge: 'LOW RISK' },
  watch: { cls: 'risk-panel--watch', badge: 'MODERATE RISK' },
  warning: { cls: 'risk-panel--warning', badge: 'HIGH RISK' },
  critical: { cls: 'risk-panel--critical', badge: 'EXTREME RISK' },
}

export default function RiskSafetyPanel({ risk }) {
  if (!risk) return null
  const tone = TONES[risk.tone] || TONES.neutral
  return (
    <section
      className={`risk-panel ${tone.cls}${risk.safety ? ' risk-panel--safety-first' : ''}`}
      aria-label="Risk and safety assessment"
      aria-live="polite"
    >
      <header className="risk-panel__header">
        <span className="risk-panel__badge" role="status">{tone.badge}</span>
        <span className="risk-panel__score">Score {Math.round(risk.score || 0)}/100</span>
      </header>
      <dl className="risk-panel__details">
        <div>
          <dt>Hazard type</dt>
          <dd>{risk.hazard}</dd>
        </div>
        <div>
          <dt>Why it matters</dt>
          <dd>{risk.explanation}</dd>
        </div>
        <div>
          <dt>Recommended action</dt>
          <dd>{risk.action}</dd>
        </div>
        {risk.source ? (
          <div>
            <dt>Source</dt>
            <dd>{risk.source}{risk.is_verified ? ' · verified ✓' : ''}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  )
}
