/**
 * ============================================================================
 * WeatherGPT · Centralized weather UI state system
 * ----------------------------------------------------------------------------
 * Converts backend weather + role-aware risk-assessment payloads and local
 * time into one predictable UI state. The backend remains the single source
 * of truth — every value here is derived from API fields, nothing is
 * hardcoded. Field names match the actual FastAPI schemas:
 *   weather:    temperature_c, apparent_temperature_c, condition,
 *               weather_code, rainfall_mm, precip_probability_pct,
 *               humidity_pct, wind_kph, wind_direction, wind_gust_kph
 *   assessment: { overall_score, overall_severity, role, risks: [...] }
 *               risk: { category, severity, score, title, explanation,
 *                       guidance[], affected_day, affected_metric }
 *
 *   getWeatherUIState(weather, assessment, currentTime) => {
 *     condition, timeOfDay, theme, background, animation,
 *     icon, riskTheme, recommendations, priority
 *   }
 * ============================================================================
 */

export const CONDITIONS = Object.freeze({
  SUNNY: 'sunny',
  PARTLY_CLOUDY: 'partly-cloudy',
  CLOUDY: 'cloudy',
  RAIN: 'rain',
  HEAVY_RAIN: 'heavy-rain',
  STORM: 'storm',
  EXTREME_HEAT: 'extreme-heat',
  STRONG_WIND: 'strong-wind',
  COLD: 'cold',
  FOG: 'fog',
  UNKNOWN: 'unknown',
})

/**
 * Prop the presenter mascot holds up to match the current weather:
 *  - 'umbrella'   → rain / heavy-rain / storm / drizzle
 *  - 'shade-card' → sunny / extreme-heat (sun-shade card)
 *  - 'card'       → everything else (plain info card)
 * Returns null before weather data loads (no prop until known).
 */
export function getWeatherProp(weather) {
  switch (getWeatherCondition(weather)) {
    case CONDITIONS.RAIN:
    case CONDITIONS.HEAVY_RAIN:
    case CONDITIONS.STORM:
      return 'umbrella'
    case CONDITIONS.SUNNY:
    case CONDITIONS.EXTREME_HEAT:
      return 'shade-card'
    case CONDITIONS.UNKNOWN:
      return null
    default:
      return 'card'
  }
}

export const TIME_OF_DAY = Object.freeze({
  MORNING: 'morning',
  AFTERNOON: 'afternoon',
  EVENING: 'evening',
  NIGHT: 'night',
})

export const RISK_LEVELS = Object.freeze({
  LOW: 'LOW',
  MODERATE: 'MODERATE',
  HIGH: 'HIGH',
  EXTREME: 'EXTREME',
})

export const PRIORITY = Object.freeze({
  NORMAL: 'normal',
  SAFETY_FIRST: 'safety-first',
})

const LEVEL_ORDER = { LOW: 1, MODERATE: 2, HIGH: 3, EXTREME: 4 }

/**
 * Direction of travel between two overall risk levels, or null when the level
 * is unchanged (or either side is unknown). Drives the mascot's celebration
 * when risk drops and its concern when risk rises.
 */
export function riskDirection(prevLevel, nextLevel) {
  const before = LEVEL_ORDER[String(prevLevel || '').toUpperCase()]
  const after = LEVEL_ORDER[String(nextLevel || '').toUpperCase()]
  if (!before || !after || before === after) return null
  return after < before ? 'improved' : 'worsened'
}

/* ----------------------------- helpers ---------------------------------- */
function toNumber(value, fallback = 0) {
  if (value === undefined || value === null || value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}
const toPct = (v) => Math.min(100, Math.max(0, toNumber(v)))

function toDate(currentTime) {
  if (currentTime instanceof Date) return currentTime
  if (typeof currentTime === 'string' && currentTime.trim()) {
    const parsed = new Date(currentTime)
    if (!Number.isNaN(parsed.getTime())) return parsed
  }
  return new Date() // display-time fallback only, never backend data
}

/* --------------------------- display formatters -------------------------- */
export function formatTemperature(value, digits = 1) {
  if (value === undefined || value === null || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(digits)}°C` : '—'
}
// Backend wind unit is kph (WeatherReading.wind_kph) — no conversion needed.
export function formatWindSpeed(valueKph) {
  const kph = Number(valueKph)
  return Number.isFinite(kph) ? `${kph.toFixed(1)} km/h` : '—'
}
export function formatPercent(value) {
  if (value === undefined || value === null || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n) ? `${Math.round(n)}%` : '—'
}

/* ------------------------------ thresholds ------------------------------- */
// Condition-classification thresholds only. Risk severities themselves are
// the backend risk engine's job (IMD bands in profiles/default.json).
const THRESHOLDS = Object.freeze({
  EXTREME_HEAT_C: 40,
  HEAT_C: 35,
  COLD_C: 5,
  STRONG_WIND_KPH: 50, // ≈ 14 m/s
  RAIN_MM: 1.0,
  HEAVY_RAIN_MM: 10,
  RAIN_PROB_PCT: 60,
  HEAVY_RAIN_PROB_PCT: 80,
})

const WMO = Object.freeze({
  CLEAR: [0],
  MAINLY_CLEAR: [1],
  PARTLY_CLOUDY: [2],
  OVERCAST: [3],
  FOG: [45, 48],
  DRIZZLE: [51, 53, 55, 56, 57],
  RAIN: [61, 63, 65, 66, 67, 80, 81],
  HEAVY_RAIN: [82],
  SNOW: [71, 73, 75, 77, 85, 86],
  STORM: [95, 96, 99],
})

/* ----------------------------- 1. time of day ---------------------------- */
export function getTimeOfDay(currentTime) {
  const h = toDate(currentTime).getHours()
  if (h >= 5 && h < 11) return TIME_OF_DAY.MORNING
  if (h >= 11 && h < 17) return TIME_OF_DAY.AFTERNOON
  if (h >= 17 && h < 20) return TIME_OF_DAY.EVENING
  return TIME_OF_DAY.NIGHT
}

/* --------------------------- 2. condition -------------------------------- */
export function getWeatherCondition(weather = {}) {
  const w = weather || {}
  // No data yet (loading/empty state) — report unknown, never a guess.
  if (w.temperature_c === undefined && w.weather_code === undefined && !w.condition) {
    return CONDITIONS.UNKNOWN
  }
  const temperatureC = toNumber(w.temperature_c)
  const apparentC = toNumber(w.apparent_temperature_c, temperatureC)
  const precipMm = toNumber(w.rainfall_mm)
  const precipProb = toPct(w.precip_probability_pct)
  const windKph = toNumber(w.wind_kph)
  const code = toNumber(w.weather_code, NaN)
  const desc = String(w.condition || '').toLowerCase()

  if (temperatureC >= THRESHOLDS.EXTREME_HEAT_C || apparentC >= THRESHOLDS.EXTREME_HEAT_C) {
    return CONDITIONS.EXTREME_HEAT
  }
  if (WMO.STORM.includes(code) || /thunder|storm/i.test(desc)) {
    return CONDITIONS.STORM
  }
  if (precipMm >= THRESHOLDS.HEAVY_RAIN_MM || WMO.HEAVY_RAIN.includes(code) ||
      (/heavy|torrential|vigorous/i.test(desc) && precipMm > 0)) {
    return CONDITIONS.HEAVY_RAIN
  }
  if (precipMm >= THRESHOLDS.RAIN_MM || precipProb >= THRESHOLDS.RAIN_PROB_PCT ||
      WMO.RAIN.includes(code) || WMO.DRIZZLE.includes(code) || /rain|drizzle|shower/i.test(desc)) {
    return precipMm >= 5 || precipProb >= THRESHOLDS.HEAVY_RAIN_PROB_PCT
      ? CONDITIONS.HEAVY_RAIN
      : CONDITIONS.RAIN
  }
  if (windKph >= THRESHOLDS.STRONG_WIND_KPH || /strong wind|gale/i.test(desc)) {
    return CONDITIONS.STRONG_WIND
  }
  if (temperatureC <= THRESHOLDS.COLD_C) {
    return CONDITIONS.COLD
  }
  if (WMO.FOG.includes(code) || /fog|mist|haze/i.test(desc)) {
    return CONDITIONS.FOG
  }
  if (WMO.OVERCAST.includes(code) || /overcast|cloudy/i.test(desc)) {
    return CONDITIONS.CLOUDY
  }
  if (WMO.PARTLY_CLOUDY.includes(code) || /partly/i.test(desc)) {
    return CONDITIONS.PARTLY_CLOUDY
  }
  if (WMO.CLEAR.includes(code) || WMO.MAINLY_CLEAR.includes(code) || /clear|sunny/i.test(desc)) {
    return CONDITIONS.SUNNY
  }
  if (temperatureC >= THRESHOLDS.HEAT_C || apparentC >= THRESHOLDS.HEAT_C) {
    return CONDITIONS.EXTREME_HEAT
  }
  if (WMO.SNOW.includes(code) || /snow|wintry/i.test(desc)) {
    return CONDITIONS.COLD
  }
  return CONDITIONS.UNKNOWN
}

/* ----------------------------- 3. risk state ----------------------------- */
// Accepts the role-aware assessment from GET /api/v1/risk (risks[] +
// overall_severity), falling back to the inline { level, score } risk object
// embedded in GET /api/v1/weather/current. Lowercase backend severities are
// normalized to the uppercase taxonomy here.
export function getRiskState(weather = {}, assessment = null) {
  const w = weather || {}
  const candidates = []

  if (assessment && Array.isArray(assessment.risks)) {
    candidates.push(...assessment.risks)
  }

  if (!candidates.length && assessment && assessment.overall_severity) {
    candidates.push({
      category: 'overall',
      severity: assessment.overall_severity,
      score: assessment.overall_score,
      title: 'Overall assessment',
      explanation: 'Overall risk level from the role-aware risk engine.',
      guidance: assessment.risks?.length ? undefined : undefined,
    })
  }

  if (!candidates.length && w.risk && (w.risk.level || w.risk.score !== undefined)) {
    candidates.push({ category: 'general', severity: w.risk.level, score: w.risk.score })
  }

  if (!candidates.length) {
    return {
      level: RISK_LEVELS.LOW, label: 'Low', score: 0,
      hazard: 'No active hazard', explanation: 'No active hazard detected by the risk engine.',
      action: 'No action required right now.', tone: 'neutral', safety: false,
      source: 'Risk Engine', is_verified: w.is_verified,
    }
  }

  let worst = null
  for (const c of candidates) {
    const raw = String(c.severity || c.level || RISK_LEVELS.LOW).toUpperCase()
    const level = LEVEL_ORDER[raw] ? raw : RISK_LEVELS.LOW
    const score = toNumber(c.score, 0)
    const guidance = Array.isArray(c.guidance) ? c.guidance.filter(Boolean) : []
    if (!worst || LEVEL_ORDER[level] > LEVEL_ORDER[worst.level]) {
      worst = {
        level,
        score,
        hazard: c.title || String(c.category || 'condition').replace(/_/g, ' '),
        explanation: c.explanation || c.description || c.reason || 'Risk engine warning — stay informed.',
        action: c.action || guidance[0] || c.recommended_action ||
          'Follow local advisories and safety guidance.',
        source: c.source || 'Risk Engine',
        is_verified: c.is_verified,
        affectedDay: c.affected_day,
        affectedMetric: c.affected_metric,
        measuredValue: c.measured_value,
      }
    }
  }

  const TONE = { LOW: 'safe', MODERATE: 'watch', HIGH: 'warning', EXTREME: 'critical' }
  const LABEL = { LOW: 'Low', MODERATE: 'Moderate', HIGH: 'High', EXTREME: 'Extreme' }
  const safety = worst.level === RISK_LEVELS.HIGH || worst.level === RISK_LEVELS.EXTREME

  return Object.assign({}, worst, {
    label: LABEL[worst.level],
    tone: TONE[worst.level],
    safety,
    is_verified: worst.is_verified === undefined ? w.is_verified : worst.is_verified,
  })
}

/* ------------------------------ 4. themes -------------------------------- */
const ICONS = Object.freeze({
  [CONDITIONS.SUNNY]: { glyph: '☀️', label: 'Sunny' },
  [CONDITIONS.PARTLY_CLOUDY]: { glyph: '⛅', label: 'Partly cloudy' },
  [CONDITIONS.CLOUDY]: { glyph: '☁️', label: 'Cloudy' },
  [CONDITIONS.RAIN]: { glyph: '🌧️', label: 'Rain' },
  [CONDITIONS.HEAVY_RAIN]: { glyph: '🌧️', label: 'Heavy rain' },
  [CONDITIONS.STORM]: { glyph: '⛈️', label: 'Storm' },
  [CONDITIONS.EXTREME_HEAT]: { glyph: '🔥', label: 'Extreme heat' },
  [CONDITIONS.STRONG_WIND]: { glyph: '💨', label: 'Strong wind' },
  [CONDITIONS.COLD]: { glyph: '❄️', label: 'Cold' },
  [CONDITIONS.FOG]: { glyph: '🌫️', label: 'Fog' },
  [CONDITIONS.UNKNOWN]: { glyph: '🌡️', label: 'Condition data pending' },
})

const SUMMARIES = Object.freeze({
  sunny: { morning: 'Bright clear morning', afternoon: 'Bright sunny afternoon', evening: 'Golden sunset skies', night: 'Clear starry night' },
  'partly-cloudy': { morning: 'Partly cloudy morning', afternoon: 'Partly cloudy afternoon', evening: 'Sunset with passing clouds', night: 'Mild night, scattered clouds' },
  cloudy: { morning: 'Cool cloudy morning', afternoon: 'Cloudy, muted daylight', evening: 'Dull cloudy evening', night: 'Overcast night' },
  rain: { morning: 'Raining morning', afternoon: 'Rainy afternoon', evening: 'Rain through the evening', night: 'Dark rainy night' },
  'heavy-rain': { morning: 'Heavy rain this morning', afternoon: 'Torrential afternoon rain', evening: 'Severe rain this evening', night: 'Heavy rain overnight' },
  storm: { morning: 'Stormy morning', afternoon: 'Storm risk this afternoon', evening: 'Stormy evening', night: 'Dramatic storm night' },
  'extreme-heat': { morning: 'Hot start to the day', afternoon: 'Warm heat environment', evening: 'Sultry evening heat', night: 'Warm humid night' },
  'strong-wind': { morning: 'Windy morning', afternoon: 'Strong winds this afternoon', evening: 'Blustery evening', night: 'Windy night' },
  cold: { morning: 'Cold morning', afternoon: 'Cold daylight', evening: 'Chilly evening', night: 'Freezing night' },
  fog: { morning: 'Foggy morning', afternoon: 'Foggy low-visibility afternoon', evening: 'Fog settling in', night: 'Foggy night' },
  unknown: { morning: 'Data settling, morning', afternoon: 'Data settling, afternoon', evening: 'Data settling, evening', night: 'Data settling, night' },
})

const CONDITION_STYLES = Object.freeze({
  sunny: {
    day: 'linear-gradient(180deg,#2e8cf5 0%,#57a9f8 38%,#8ec8fb 68%,#dcf2ff 100%)',
    night: 'linear-gradient(180deg,#0a1128 0%,#111c40 45%,#1c2f5e 100%)',
    accent: 'rgba(255,209,102,.5)', animation: 'sunlight',
  },
  'partly-cloudy': {
    day: 'linear-gradient(180deg,#4b93e8 0%,#86b6ea 45%,#c6dcf4 100%)',
    night: 'linear-gradient(180deg,#0c1230 0%,#152447 55%,#24365f 100%)',
    accent: 'rgba(255,217,160,.5)', animation: 'clouds',
  },
  cloudy: {
    day: 'linear-gradient(180deg,#6d86a3 0%,#93a9bd 55%,#b9c6d4 100%)',
    night: 'linear-gradient(180deg,#0a1424 0%,#12203a 55%,#1c2c47 100%)',
    accent: 'rgba(207,224,234,.55)', animation: 'clouds',
  },
  rain: {
    day: 'linear-gradient(180deg,#4a6072 0%,#748795 60%,#94a3ae 100%)',
    night: 'linear-gradient(180deg,#05080f 0%,#0d1626 55%,#1a2639 100%)',
    accent: 'rgba(127,180,222,.55)', animation: 'rain',
  },
  'heavy-rain': {
    day: 'linear-gradient(180deg,#2c3850 0%,#55677d 55%,#7c8b99 100%)',
    night: 'linear-gradient(180deg,#04070d 0%,#0a111f 50%,#182438 100%)',
    accent: 'rgba(158,197,234,.55)', animation: 'rain',
  },
  storm: {
    day: 'linear-gradient(180deg,#232c3e 0%,#4a5a70 50%,#6d7c8c 100%)',
    night: 'linear-gradient(180deg,#03050c 0%,#0a0e1c 55%,#141d32 100%)',
    accent: 'rgba(255,215,106,.5)', animation: 'storm',
  },
  'extreme-heat': {
    day: 'linear-gradient(180deg,#ff7a1a 0%,#ffab4a 45%,#ffd9a3 100%)',
    night: 'linear-gradient(180deg,#2a1205 0%,#4b2210 55%,#6d3a1c 100%)',
    accent: 'rgba(255,176,40,.55)', animation: 'heat',
  },
  'strong-wind': {
    day: 'linear-gradient(180deg,#5c86b0 0%,#8fb0cf 50%,#c2d4e6 100%)',
    night: 'linear-gradient(180deg,#0a1226 0%,#14223f 55%,#223456 100%)',
    accent: 'rgba(188,216,242,.5)', animation: 'wind',
  },
  cold: {
    day: 'linear-gradient(180deg,#7f9fc7 0%,#a9c1dd 55%,#d6e2f2 100%)',
    night: 'linear-gradient(180deg,#141a3a 0%,#232e58 55%,#3a4a7d 100%)',
    accent: 'rgba(191,224,255,.55)', animation: 'frost',
  },
  fog: {
    day: 'linear-gradient(180deg,#8b9aa8 0%,#aab7c1 60%,#c9d2d8 100%)',
    night: 'linear-gradient(180deg,#0d1322 0%,#182236 55%,#26344a 100%)',
    accent: 'rgba(220,228,234,.55)', animation: 'fog',
  },
  unknown: {
    day: 'linear-gradient(180deg,#42596e 0%,#6d8191 60%,#9aa9b4 100%)',
    night: 'linear-gradient(180deg,#0a0f1c 0%,#131c30 55%,#1f2b45 100%)',
    accent: 'rgba(199,214,224,.5)', animation: 'clouds',
  },
})

const TIME_OVERLAYS = Object.freeze({
  morning: 'rgba(255,178,102,.10)',
  afternoon: 'rgba(255,255,240,.06)',
  evening: 'rgba(255,138,74,.13)',
  night: null,
})

function buildTheme(condition, timeOfDay, priority) {
  const base = CONDITION_STYLES[condition] || CONDITION_STYLES.unknown
  const isNight = timeOfDay === TIME_OF_DAY.NIGHT
  const safety = priority === PRIORITY.SAFETY_FIRST
  const animation = isNight && condition === CONDITIONS.SUNNY ? 'starry-night' : base.animation
  const summaries = SUMMARIES[condition] || SUMMARIES.unknown

  return {
    key: `${condition}--${timeOfDay}${safety ? '--safety' : ''}`,
    summary: `${summaries[timeOfDay]}${safety ? ' · safety-first mode active' : ''}`,
    gradient: isNight ? base.night : base.day,
    accent: base.accent,
    timeOverlay: TIME_OVERLAYS[timeOfDay],
    animation,
    isNight,
    safety,
  }
}

/* ------------------------- 5. recommendations ---------------------------- */
const CONDITION_RECS = Object.freeze({
  sunny: ['Light clothing and sun protection recommended.', 'UV exposure peaks at midday — wear sunscreen outdoors.'],
  'partly-cloudy': ['Pleasant partly-cloudy conditions — most outdoor activity is fine.'],
  cloudy: ['Overcast skies reduce visibility — drive with extra care.'],
  rain: ['Rain in progress — carry an umbrella and allow extra travel time.', 'Roads may be slippery — reduce speed.'],
  'heavy-rain': ['Heavy rain — avoid low-lying areas and riverbanks.', 'Avoid waterlogged roads and never drive through unknown-depth water.'],
  storm: ['Thunderstorm — stay indoors, away from open fields, tall trees and water bodies.', 'Unplug sensitive equipment during lightning.'],
  'extreme-heat': ['Extreme heat — stay hydrated and avoid exertion between 11:00 and 16:00.', 'Check on vulnerable neighbours; keep pets indoors with water.'],
  'strong-wind': ['Strong winds — secure loose objects, hoardings and scaffolding.', 'Avoid parking under trees; postpone rooftop work.'],
  cold: ['Cold conditions — wear warm layers and cover extremities.', 'Protect exposed pipes and sensitive crops from frost.'],
  fog: ['Fog reduces visibility — use fog lamps and keep a safe following distance.'],
  unknown: ['Condition data pending — take standard precautions.'],
})

const TIME_RECS = Object.freeze({
  morning: 'Morning hours — allow extra time if visibility is low.',
  afternoon: 'Afternoon heat — plan outdoor work around cooler hours.',
  evening: 'Evening — visibility drops after sunset; switch on headlights early.',
  night: 'Night — use low beam in dark stretches and watch for animals on roads.',
})

function buildRecommendations(condition, timeOfDay, risk) {
  const list = (CONDITION_RECS[condition] || []).slice()
  if (risk && risk.level !== RISK_LEVELS.LOW && risk.action) list.unshift(risk.action)
  list.push(TIME_RECS[timeOfDay])
  return Array.from(new Set(list.map((s) => s.trim()).filter(Boolean)))
}

/* ---------------------------- 6. public API ------------------------------ */
export function getWeatherUIState(weather = {}, assessment = null, currentTime = new Date()) {
  const wx = weather || {}
  const condition = getWeatherCondition(wx)
  const timeOfDay = getTimeOfDay(currentTime)
  const riskTheme = getRiskState(wx, assessment)
  const priority = riskTheme.safety ? PRIORITY.SAFETY_FIRST : PRIORITY.NORMAL
  const theme = buildTheme(condition, timeOfDay, priority)

  return {
    condition,
    timeOfDay,
    priority,
    theme,
    background: theme.gradient,
    animation: theme.animation,
    icon: ICONS[condition],
    riskTheme,
    recommendations: buildRecommendations(condition, timeOfDay, riskTheme),
  }
}
