import { useEffect, useRef, useState } from 'react'
import { riskDirection } from '../weather/ui-state'

// Watches the app's overall risk level and reports a short-lived trend burst —
// 'improved' when risk drops, 'worsened' when it rises — so the mascot can
// celebrate or look concerned. The burst clears itself after BURST_MS so this
// reads as a reaction to the change, not a permanent mood.
const BURST_MS = 6500

export function useRiskTrend(level) {
  const [trend, setTrend] = useState(null)
  const prev = useRef(null)
  const timer = useRef(null)

  useEffect(() => {
    if (!level) return
    const direction = riskDirection(prev.current, level)
    prev.current = level
    if (!direction) return
    setTrend(direction)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setTrend(null), BURST_MS)
    // Deliberately no per-change cleanup: the burst timer is owned by the
    // latest change only, and clearing here would leave the trend stuck on
    // React's double-invoked effects in development.
  }, [level])

  useEffect(() => () => clearTimeout(timer.current), [])

  return trend
}

export default useRiskTrend
