// Thin API client. All backend calls go through here so the base URL,
// error handling, and response shapes stay in one place. There is
// deliberately exactly one HTTP client in this app — import { api }.

const BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    // FastAPI validation errors (422) carry a readable detail[0].msg;
    // other errors carry detail as a string. Surface the friendliest one.
    let detail = ''
    try {
      const body = await res.json()
      if (Array.isArray(body.detail) && body.detail[0]) {
        detail = body.detail[0].msg || JSON.stringify(body.detail[0])
      } else if (typeof body.detail === 'string') {
        detail = body.detail
      }
    } catch {
      const text = await res.text().catch(() => '')
      detail = text.slice(0, 200)
    }
    const error = new Error(detail || `Request to ${path} failed (HTTP ${res.status})`)
    error.status = res.status
    throw error
  }
  return res.json()
}

export const api = {
  // Weather data
  getCurrentWeather: (latitude, longitude, scenario = 'normal') =>
    request(`/weather/current?latitude=${latitude}&longitude=${longitude}&scenario=${scenario}`),

  getForecast: (latitude, longitude, days = 7, scenario = 'normal') =>
    request(`/weather/forecast?latitude=${latitude}&longitude=${longitude}&days=${days}&scenario=${scenario}`),

  getRisk: (latitude, longitude, role = 'customer', scenario = 'normal') =>
    request(`/risk?latitude=${latitude}&longitude=${longitude}&role=${role}&scenario=${scenario}`),

  getSafety: (latitude, longitude, role = 'customer', scenario = 'normal') =>
    request(`/safety?latitude=${latitude}&longitude=${longitude}&role=${role}&scenario=${scenario}`),

  // Side features
  getSafeZones: (latitude, longitude) =>
    request(`/safe-zones/nearby?latitude=${latitude}&longitude=${longitude}`),

  // Location search (Open-Meteo geocoding, key-less). Returns places with
  // latitude/longitude ready for the other endpoints; unknown names are a
  // valid empty list, not an error.
  searchLocations: (query, count = 5) =>
    request(`/geo/search?query=${encodeURIComponent(query)}&count=${count}`),

  sendChatMessage: ({ message, sessionId, language, latitude, longitude, scenario, role = 'customer' }) =>
    request(`/chat/send`, {
      method: 'POST',
      body: JSON.stringify({
        message,
        session_id: sessionId,
        language,
        latitude,
        longitude,
        role,
        scenario,
      }),
    }),

  triggerSos: ({ latitude, longitude, note }) =>
    request(`/sos/trigger`, {
      method: 'POST',
      body: JSON.stringify({ latitude, longitude, note }),
    }),
}
