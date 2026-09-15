import { useState } from 'react'
import { api } from '../lib/api'
import { t } from '../i18n'

const CONTACTS = [
  { name: 'Amit Sharma (Brother)', phone: '+91 90000 00001' },
  { name: 'Local NDRF Helpline', phone: '1078 (National Disaster Helpline)' },
]

export default function SosModal({ open, onClose, latitude, longitude, language = 'en' }) {
  const [result, setResult] = useState(null)
  const [sending, setSending] = useState(false)

  if (!open) return null

  async function confirmSos() {
    setSending(true)
    try {
      const res = await api.triggerSos({ latitude, longitude, note: 'Triggered from web app' })
      setResult(res)
    } catch {
      setResult({ message: 'Could not log the SOS event — check your connection and try again.' })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[2000] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-navy-900 border border-border rounded-2xl p-5 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-display font-bold text-lg mb-2">{t(language, 'sosTitle')}</h3>
        {!result ? (
          <>
            <p className="text-sm text-slate-100 leading-relaxed mb-3">{t(language, 'sosBody')}</p>
            <div className="flex flex-col gap-1.5 mb-4">
              {CONTACTS.map((c) => (
                <div key={c.phone} className="flex justify-between text-[13px] bg-navy-700 rounded-lg px-3 py-2">
                  <span>{c.name}</span>
                  <span className="font-mono">{c.phone}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button className="px-4 py-2 rounded-full text-xs border border-border" onClick={onClose}>
                {t(language, 'cancel')}
              </button>
              <button
                className="px-4 py-2 rounded-full text-xs bg-red-600 text-white font-semibold disabled:opacity-60"
                onClick={confirmSos}
                disabled={sending}
              >
                {sending ? t(language, 'logging') : t(language, 'logSos')}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-100 leading-relaxed mb-4">🆘 {result.message}</p>
            <div className="flex justify-end">
              <button className="px-4 py-2 rounded-full text-xs bg-sky text-navy-950 font-semibold" onClick={onClose}>
                {t(language, 'close')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
