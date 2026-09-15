const LEVEL_COLOR = {
  low: '#22c55e',
  moderate: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
}

export default function RiskGauge({ score = 0, level = 'low', explanation }) {
  const color = LEVEL_COLOR[level] || LEVEL_COLOR.low
  const radius = 62
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(100, score)) / 100
  const offset = circumference * (1 - pct)

  return (
    <div className="flex flex-col items-center justify-center flex-1">
      <div className="relative w-40 h-40">
        <svg viewBox="0 0 160 160" className="w-40 h-40 -rotate-90">
          <circle cx="80" cy="80" r={radius} fill="none" stroke="#16294d" strokeWidth="14" />
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 0.6s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="font-display font-bold text-xl" style={{ color }}>
            {level.toUpperCase()}
          </div>
          <div className="font-mono text-xs text-slate-300 mt-0.5">{score.toFixed(0)}/100</div>
        </div>
      </div>
      {explanation && <p className="text-xs text-slate-100 leading-relaxed mt-3 text-center">{explanation}</p>}
    </div>
  )
}
