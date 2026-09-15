// Role selector: switches how risks are prioritized and explained.
// Pure client-side state + a backend re-fetch — no page reload. The
// selection persists in localStorage and defaults to CUSTOMER.
import { t } from '../i18n'

export const ROLES = [
  { value: 'customer', labelKey: 'roleCustomer', icon: '👤' },
  { value: 'farmer', labelKey: 'roleFarmer', icon: '🌾' },
  { value: 'traveler', labelKey: 'roleTraveler', icon: '🧳' },
  { value: 'disaster_management_officer', labelKey: 'roleOfficer', icon: '🏛️' },
]

export const DEFAULT_ROLE = 'customer'

export function getStoredRole() {
  try {
    const stored = window.localStorage.getItem('weathergpt_role')
    return ROLES.some((r) => r.value === stored) ? stored : DEFAULT_ROLE
  } catch {
    return DEFAULT_ROLE
  }
}

export function storeRole(role) {
  try {
    window.localStorage.setItem('weathergpt_role', role)
  } catch {
    // Private mode / storage disabled: selection just won't persist.
  }
}

export default function RoleSelector({ role, onChange, language = 'en' }) {
  return (
    <section aria-label={t(language, 'roleSelectorLabel')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <h2 className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold mb-2.5">
        {t(language, 'viewAs')}
      </h2>
      <div role="radiogroup" aria-label={t(language, 'viewAs')} className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {ROLES.map(({ value, labelKey, icon }) => {
          const selected = role === value
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(value)}
              className={`flex items-center gap-2 justify-center px-2.5 py-2.5 rounded-xl text-[12px] font-semibold border transition ${
                selected
                  ? 'bg-sky/20 border-sky text-slate-100'
                  : 'bg-navy-700 border-border text-slate-300 hover:border-sky/60'
              }`}
            >
              <span aria-hidden="true">{icon}</span>
              {t(language, labelKey)}
            </button>
          )
        })}
      </div>
    </section>
  )
}
