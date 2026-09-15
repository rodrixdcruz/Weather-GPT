import { I18N, t } from '../i18n'

export default function LanguageModal({ open, onClose, currentLang, onSelect }) {
  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/60 z-[2000] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-navy-900 border border-border rounded-2xl p-5 max-w-xs w-full" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display font-bold text-lg mb-3">{t(currentLang, 'chooseLanguage')}</h3>
        <div className="flex flex-col gap-1.5">
          {Object.entries(I18N).map(([code, v]) => (
            <button
              key={code}
              className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm text-left ${
                code === currentLang ? 'bg-sky/15 border border-sky/40' : 'bg-navy-700 border border-transparent'
              }`}
              onClick={() => onSelect(code)}
            >
              <span>{v.name}</span>
              {code === currentLang && <span>✓</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
