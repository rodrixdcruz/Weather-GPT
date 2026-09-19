import { t } from '../i18n'

// The scenario picker (Normal / Heavy Rainfall / …) is deliberately gone:
// weather is detected from the location and the live provider, so choosing a
// fake scenario was a demo-only control that contradicted the real data on
// screen. The app now always reads the `normal` path, which is what live
// providers (open_meteo) ignore anyway — `scenario` only ever selected a
// fixed fixture set in the `mock` provider.
export default function TopBar({
  langLabel,
  onLangClick,
  onSosClick,
  language,
  weather = null,
  session = null,
  onLogout,
  onAdminClick,
  onTourClick,
  onJudgeClick,
  isJudge = false,
}) {
  const user = session?.user
  const isAdmin = Boolean(user?.is_admin)
  return (
    <>
      <div className="flex items-center justify-between gap-2.5 px-5 py-3.5 border-b border-border bg-navy-950/70 backdrop-blur sticky top-0 z-50 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8.5 h-8.5 w-[34px] h-[34px] rounded-[9px] bg-gradient-to-br from-sky to-[#1c5fb0] flex items-center justify-center font-bold text-white text-sm">
            WG
          </div>
          <div>
            <h1 className="font-display font-bold text-[17px] m-0">MausamBagha AI</h1>
            <small className="block text-slate-300 text-[10.5px] uppercase tracking-wide">
              {t(language, 'brandSub')}
            </small>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            className="bg-navy-800 border border-border text-slate-100 px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 hover:border-sky transition"
            onClick={onLangClick}
          >
            🌐 {langLabel}
          </button>

          <button
            data-tour="sos"
            className="bg-gradient-to-br from-red-500 to-red-700 border-none text-white font-bold tracking-wide px-4 py-2 rounded-full text-xs animate-sos"
            onClick={onSosClick}
          >
            {t(language, 'sos')}
          </button>

          {/* Guided feature tour — one click away for any user, auto-opened
              for the judge account (see FeatureTour.jsx). */}
          <button
            data-tour="tour-button"
            className="bg-navy-800 border border-border text-slate-100 px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 hover:border-sky transition"
            onClick={onTourClick}
          >
            ✨ {t(language, 'tourHeaderButton')}
          </button>

          {/* Judge demo console: rendered ONLY for the judge session (the
              backend gates the actual simulation independently). */}
          {isJudge && (
            <button
              className="bg-gradient-to-br from-fuchsia-600 to-purple-700 border-none text-white px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1.5 hover:brightness-110 transition"
              onClick={onJudgeClick}
            >
              🧑‍⚖️ {t(language, 'judgePanel')}
            </button>
          )}

          {/* Admin panel is admin-only; the backend enforces it too. */}
          {isAdmin && (
            <button
              className="bg-navy-800 border border-sky/60 text-sky px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 hover:bg-sky/10 transition"
              onClick={onAdminClick}
            >
              🛠️ {t(language, 'adminPanel')}
            </button>
          )}

          {user && (
            <div className="flex items-center gap-2 pl-2.5 border-l border-border">
              <div className="text-right leading-tight">
                <div className="text-[11.5px] font-semibold text-slate-100">{user.display_name || user.username}</div>
                <div className="text-[10px] text-slate-400">
                  🔒 {t(language, `role_${session.role}`)}
                </div>
              </div>
              <button
                className="bg-navy-800 border border-border text-slate-200 px-3 py-1.5 rounded-full text-xs hover:border-sky transition"
                onClick={onLogout}
                title={t(language, 'roleLockedNote')}
              >
                {t(language, 'logout')}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Data-source banner: reflects the ACTUAL source of the data being
          shown. Live = verified provider readings (e.g. Open-Meteo);
          demo = mock fixtures or unknown/loading — never the reverse. */}
      {weather?.is_verified ? (
        <div className="bg-[repeating-linear-gradient(135deg,#0a2f1c,#0a2f1c_10px,#0c3320_10px,#0c3320_20px)] border-b border-[#1d6b43] text-[#9ff0c6] text-xs px-5 py-2 flex items-center gap-2.5 flex-wrap justify-between">
          <span>✓ {t(language, 'liveBanner')}</span>
        </div>
      ) : (
        <div className="bg-[repeating-linear-gradient(135deg,#3a2f0a,#3a2f0a_10px,#33290a_10px,#33290a_20px)] border-b border-[#6b5210] text-[#ffd873] text-xs px-5 py-2 flex items-center gap-2.5 flex-wrap justify-between">
          <span>⚠ {t(language, 'demoBanner')}</span>
        </div>
      )}
    </>
  )
}
