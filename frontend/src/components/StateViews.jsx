// Reusable loading / error / empty state views, so no screen in the app
// ever shows a raw exception or a blank region. Each view is accessible:
// role="status"/"alert" and a fixed-height skeleton avoid layout shift.
import { t } from '../i18n'

export function LoadingState({ language = 'en', label, height = 'h-40' }) {
  return (
    <div role="status" aria-live="polite" className={`${height} flex flex-col items-center justify-center gap-3 text-slate-300`}>
      <div className="w-8 h-8 rounded-full border-2 border-border border-t-sky animate-spin" aria-hidden="true" />
      <span className="text-xs">{label || t(language, 'loading')}</span>
    </div>
  )
}

export function SkeletonCard({ height = 'h-40' }) {
  return <div className={`animate-pulse bg-navy-700/50 rounded-xl w-full ${height}`} aria-hidden="true" />
}

export function ErrorState({ language = 'en', message, onRetry, height = 'h-40' }) {
  return (
    <div role="alert" className={`${height} flex flex-col items-center justify-center gap-3 text-center px-4`}>
      <span aria-hidden="true" className="text-2xl">⚠️</span>
      <p className="text-[13px] text-slate-100 leading-relaxed max-w-xs">
        {t(language, 'errorTitle')}
        {message ? <span className="block text-slate-300 text-xs mt-1">{message}</span> : null}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-4 py-2 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition font-semibold"
        >
          {t(language, 'retry')}
        </button>
      )}
    </div>
  )
}

export function EmptyState({ language: _language = 'en', icon = '✅', message, height = 'h-40' }) {
  return (
    <div role="status" className={`${height} flex flex-col items-center justify-center gap-2 text-center px-4`}>
      <span aria-hidden="true" className="text-2xl">{icon}</span>
      <p className="text-[13px] text-slate-100 leading-relaxed max-w-xs">{message}</p>
    </div>
  )
}
