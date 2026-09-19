// Login screen. The role is chosen HERE, once, and cannot be changed again
// without signing out — the backend copies it onto the session row and
// resolves every later request from that session, so the lock is enforced
// server-side, not just in this UI.
//
// No role is preselected: the user must make a deliberate choice.
import { useState } from 'react'
import { I18N, t } from '../i18n'
import { ROLES } from './RoleSelector'

export default function LoginPage({ language, onLanguageChange, onSignIn }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    if (!role) {
      setError(t(language, 'loginRoleRequired'))
      return
    }
    setBusy(true)
    try {
      await onSignIn({ username: username.trim(), password, role })
    } catch (err) {
      setError(err?.message || t(language, 'loginError'))
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-5">
      <div className="w-full max-w-[560px]">
        {/* Brand */}
        <div className="flex items-center justify-center gap-2.5 mb-5">
          <div className="w-[38px] h-[38px] rounded-[10px] bg-gradient-to-br from-sky to-[#1c5fb0] flex items-center justify-center font-bold text-white text-[15px]">
            WG
          </div>
          <div className="text-left">
            <h1 className="font-display font-bold text-[19px] m-0">MausamBagha AI</h1>
            <small className="block text-slate-300 text-[10.5px] uppercase tracking-wide">
              {t(language, 'brandSub')}
            </small>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-5 flex flex-col gap-4"
        >
          <div>
            <h2 className="text-[16px] font-semibold m-0">{t(language, 'loginTitle')}</h2>
            <p className="text-slate-300 text-[12px] m-0 mt-1">{t(language, 'loginSubtitle')}</p>
          </div>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
            {t(language, 'loginUsername')}
            <input
              className="bg-navy-700 border border-border rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky"
              value={username}
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
            {t(language, 'loginPassword')}
            <input
              type="password"
              className="bg-navy-700 border border-border rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {/* One-time role choice — the core of this screen. */}
          <fieldset className="border-none p-0 m-0 flex flex-col gap-2">
            <legend className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold mb-2 p-0">
              {t(language, 'loginChooseRole')}
            </legend>
            <div role="radiogroup" aria-label={t(language, 'loginChooseRole')} className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {ROLES.map(({ value, labelKey, icon }) => {
                const selected = role === value
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setRole(value)}
                    className={`text-left px-3 py-2.5 rounded-xl border transition ${
                      selected
                        ? 'bg-sky/20 border-sky text-slate-100'
                        : 'bg-navy-700 border-border text-slate-300 hover:border-sky/60'
                    }`}
                  >
                    <span className="flex items-center gap-2 text-[12.5px] font-semibold">
                      <span aria-hidden="true">{icon}</span>
                      {t(language, labelKey)}
                    </span>
                    <span className="block text-[10.5px] text-slate-400 mt-0.5">
                      {t(language, `${labelKey}Desc`)}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="text-[10.5px] text-yellow-400 m-0 mt-1">🔒 {t(language, 'loginRoleLocked')}</p>
            {role === 'judge' && (
              <p className="text-[10.5px] text-sky m-0 mt-1">✨ {t(language, 'tourWelcomeBody')}</p>
            )}
          </fieldset>

          {error && (
            <div role="alert" className="text-[11.5px] text-red-300 bg-red-500/10 border border-red-500/40 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2.5 rounded-full text-[13px] font-semibold bg-sky text-navy-950 disabled:opacity-60"
          >
            {busy ? t(language, 'loginBusy') : t(language, 'loginSubmit')}
          </button>

          {/* The seeded demo credentials are deliberately NOT advertised here:
              printing a working username/password on the sign-in screen hands
              them to anyone who reaches the page. */}
          <div className="border-t border-border pt-3 flex items-center justify-end gap-2 flex-wrap">
            <div className="flex gap-1.5">
              {Object.entries(I18N).map(([code, dict]) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => onLanguageChange(code)}
                  className={`px-2.5 py-1 rounded-full text-[10.5px] border transition ${
                    language === code ? 'bg-sky/20 border-sky text-slate-100' : 'bg-navy-800 border-border text-slate-300 hover:border-sky/60'
                  }`}
                >
                  {dict.name.split(' ')[0]}
                </button>
              ))}
            </div>
          </div>
        </form>

        <p className="text-[10.5px] text-slate-400 text-center mt-3 px-2">{t(language, 'loginNote')}</p>
      </div>
    </div>
  )
}
