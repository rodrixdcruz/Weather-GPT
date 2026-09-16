// Dashboard session: who is signed in and which role is LOCKED IN for them.
//
// The role is chosen once on the login screen and owned by the backend
// session; this module only mirrors it for the UI. There is deliberately no
// `setRole` — changing the role requires signing out and back in.
//
// Security note: the token is a bearer credential, so it lives in
// localStorage. That is acceptable for this local-first dashboard; a
// production deployment should move it to an HttpOnly cookie set by the
// backend.
import { useCallback, useEffect, useState } from 'react'
import { api, setAuthToken } from './api'

const STORAGE_KEY = 'weathergpt_session'

// Fired when the backend rejects our token (expired/revoked), so the app can
// drop the user back to the login screen instead of showing broken panels.
export const UNAUTHORIZED_EVENT = 'weathergpt:unauthorized'

export function loadSession() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.token || !parsed?.user) return null
    if (parsed.expires_at && new Date(parsed.expires_at).getTime() <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function saveSession(session) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Storage disabled: the session simply won't survive a reload.
  }
  setAuthToken(session?.token || null)
}

export function clearSession() {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing to do.
  }
  setAuthToken(null)
}

export function useSession() {
  const [session, setSession] = useState(() => loadSession())

  // Keep the API client's token in sync from the very first render.
  useEffect(() => {
    setAuthToken(session?.token || null)
  }, [session])

  // A 401 from any endpoint means the session is gone (expired or revoked).
  useEffect(() => {
    const onUnauthorized = () => {
      clearSession()
      setSession(null)
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const signIn = useCallback(async ({ username, password, role }) => {
    const next = await api.login({ username, password, role })
    saveSession(next)
    setSession(next)
    return next
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // Signing out locally must succeed even if the call fails.
    }
    clearSession()
    setSession(null)
  }, [])

  return { session, signIn, signOut }
}
