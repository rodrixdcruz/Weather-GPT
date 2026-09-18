// Locked-role indicator.
//
// The role is chosen ONCE on the login screen and owned by the backend
// session, so in the dashboard it is a single read-only line — not a control.
// Showing four disabled cards implied a choice that does not exist here; the
// only way to change role is to log out.
//
// This is display only, never a gate: the backend resolves the role for every
// request from the session and ignores whatever the client asks for.
//
// `ROLES` is still exported because the login screen uses it to build its
// picker — that is the one place a role is actually chosen.
import { t } from '../i18n'

export const ROLES = [
  { value: 'customer', labelKey: 'roleCustomer', icon: '👤' },
  { value: 'farmer', labelKey: 'roleFarmer', icon: '🌾' },
  { value: 'traveler', labelKey: 'roleTraveler', icon: '🧳' },
  { value: 'disaster_management_officer', labelKey: 'roleOfficer', icon: '🏛️' },
  // Judge card: the backend normalizes the unknown 'judge' role to the
  // citizen view (normalize_role), so judges see the full app — and the
  // session comes back flagged is_judge, which auto-opens the feature tour.
  { value: 'judge', labelKey: 'roleJudge', icon: '🧑‍⚖️' },
]

// No DEFAULT_ROLE and no persistence: the role is never "defaulted" or
// remembered on the client — the session owns it.

export default function RoleSelector({ role, language = 'en', locked = false }) {
  const current = ROLES.find((entry) => entry.value === role)
  return (
    <section
      aria-label={t(language, 'roleSelectorLabel')}
      className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl px-4 py-2.5 flex items-center gap-3 flex-wrap"
    >
      <h2 className="text-[11px] uppercase tracking-wide text-slate-400 font-semibold m-0">
        {t(language, 'roleLabel')}
      </h2>
      <span className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-[12px] font-semibold border bg-sky/20 border-sky text-slate-100">
        <span aria-hidden="true">{current?.icon}</span>
        {t(language, current ? current.labelKey : `role_${role}`)}
      </span>
      {locked && (
        <span className="text-[10.5px] text-yellow-400 font-semibold">
          🔒 {t(language, 'roleLockedNote')}
        </span>
      )}
    </section>
  )
}
