// Thin API client. All backend calls go through here so the base URL,
// error handling, and response shapes stay in one place. There is
// deliberately exactly one HTTP client in this app — import { api }.

// VITE_API_BASE_URL is baked in at BUILD time, so a stale value survives every
// later fix: a dead tunnel, or an http://localhost:8000 left over from local
// development, keeps breaking a deployed build until it is rebuilt without it.
//
// One case is guarded here. A plain-http base on an https page can NEVER
// succeed — the browser refuses the request as mixed content before it leaves
// the page, and the only symptom is "Failed to fetch" with nothing in the
// network log. Retrying or guessing is not safe (this client posts SOS and chat
// messages, which must never be duplicated), so the value is simply dropped in
// favour of the same-origin /api/v1, which the host proxy forwards to backend.
//
// Every other configured value is honoured unchanged: silently rewriting a
// reachable backend URL would hide real misconfiguration.
const configuredBase = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')

const SAME_ORIGIN_BASE = '/api/v1'

function resolveBase() {
  if (!configuredBase) return SAME_ORIGIN_BASE

  const pageIsSecure =
    typeof window !== 'undefined' && window.location.protocol === 'https:'
  if (pageIsSecure && configuredBase.startsWith('http://')) {
    console.warn(
      `[weathergpt] Ignoring VITE_API_BASE_URL (${configuredBase}): an http:// API cannot be ` +
        `called from this https:// page, so the browser would block every request as mixed ` +
        `content. Falling back to ${SAME_ORIGIN_BASE}. Remove the variable from the deploy ` +
        `environment and rebuild, or point it at an https:// backend.`,
    )
    return SAME_ORIGIN_BASE
  }

  return configuredBase
}

const BASE = resolveBase()

// The dashboard session token, mirrored here so every request carries it
// without each call site passing it around. session.js owns the value.
let authToken = null

export function setAuthToken(token) {
  authToken = token || null
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(authToken ? { 'X-Session-Token': authToken } : {}),
    },
    ...options,
  })

  // An expired or revoked session is a state change the app must react to
  // (back to the login screen), not just an error string on one panel.
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('weathergpt:unauthorized'))
  }
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
  // --- Session / auth ---
  login: ({ username, password, role }) =>
    request(`/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ username, password, role }),
    }),

  getSession: () => request(`/auth/session`),

  logout: () => request(`/auth/logout`, { method: 'POST' }),

  // --- Admin panel (admin accounts only) ---
  getAdminOverview: () => request(`/admin/overview`),

  getAdminSessions: () => request(`/admin/sessions`),

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

  // Road routing via the backend's OSRM proxy (see lib/routing.js for the
  // shape helpers and error semantics). The abort signal is separated from
  // the query params and handed to fetch itself.
  getRoute: ({ signal, ...params }) =>
    request(`/routing/route?${new URLSearchParams(params)}`, { signal }),

  getTravelTimes: ({ signal, ...params }) =>
    request(`/routing/travel-times?${new URLSearchParams(params)}`, { signal }),

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
