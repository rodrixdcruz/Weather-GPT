// Guided feature tour — a spotlight walkthrough of everything MausamBagha AI does,
// built for hackathon judges and first-time visitors.
//
// Zero dependencies: one full-screen overlay renders a transparent "window"
// over the targeted element (box-shadow spotlight, pointer-events pass-through
// so the highlighted control stays usable) plus a floating card with the step
// copy. Targets are found by [data-tour="id"] attributes, so components keep
// no knowledge of the tour.
//
// Opens automatically for the judge account (session.user.is_judge) and from
// the header button for everyone. Position re-computes on scroll/resize so
// the spotlight never detaches from its target.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { t } from '../i18n'

export const TOUR_STEPS = [
  { id: 'weather', titleKey: 'tourWeatherTitle', bodyKey: 'tourWeatherBody' },
  { id: 'risk-cards', titleKey: 'tourRiskTitle', bodyKey: 'tourRiskBody' },
  { id: 'risk-gauge', titleKey: 'tourGaugeTitle', bodyKey: 'tourGaugeBody' },
  { id: 'chat', titleKey: 'tourChatTitle', bodyKey: 'tourChatBody' },
  { id: 'forecast', titleKey: 'tourForecastTitle', bodyKey: 'tourForecastBody' },
  { id: 'shelter-map', titleKey: 'tourMapTitle', bodyKey: 'tourMapBody' },
  { id: 'shelter-list', titleKey: 'tourSheltersTitle', bodyKey: 'tourSheltersBody' },
  { id: 'sos', titleKey: 'tourSosTitle', bodyKey: 'tourSosBody' },
]

function findTarget(id) {
  return document.querySelector(`[data-tour="${id}"]`)
}

export default function FeatureTour({ open, step, onStepChange, onClose, language }) {
  const [rect, setRect] = useState(null)
  const nextRef = useRef(null)

  const total = TOUR_STEPS.length
  const current = TOUR_STEPS[step]
  const isLast = step === total - 1

  // Measure the current target after every step change and on reflow.
  // Two subtleties this has to survive:
  // 1. Cards backed by async data (weather, shelters) mount AFTER the tour
  //    can open — keep polling briefly instead of spotlighting nothing.
  // 2. The dashboard is a long scrolling page: bring the target into view
  //    ONCE when it first appears (never from the scroll listener, or the
  //    auto-scroll would fight itself forever), then track it as it moves.
  useLayoutEffect(() => {
    if (!open || !current) return undefined
    let raf = 0
    let attempts = 0
    let scrolled = false
    const measure = () => {
      const el = findTarget(current.id)
      if (!el) {
        setRect(null)
        // ~5 s of 60 fps polling, then give up and center the card.
        if (attempts < 300) {
          attempts += 1
          raf = requestAnimationFrame(measure)
        }
        return
      }
      if (!scrolled) {
        scrolled = true
        const r = el.getBoundingClientRect()
        if (r.top < 80 || r.bottom > window.innerHeight - 80) {
          el.scrollIntoView({ block: 'center', behavior: 'smooth' })
        }
      }
      setRect(el.getBoundingClientRect())
    }
    measure()
    // Capture phase: scrolls inside the page container count too.
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
      cancelAnimationFrame(raf)
    }
  }, [open, current])

  // Keyboard: Escape exits, arrows navigate. Body scroll is deliberately NOT
  // locked — the spotlight follows the viewport, scrolling is part of the
  // tour (and the overlay's dimmer lets wheel events through), so locking it
  // would both fight the auto-scroll and trap tall targets.
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight' && !isLast) onStepChange(step + 1)
      if (event.key === 'ArrowLeft' && step > 0) onStepChange(step - 1)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, step, isLast, onStepChange, onClose])

  // Keep focus management simple but honest: the primary button gets focus
  // per step so Enter advances the tour.
  useEffect(() => {
    if (open) nextRef.current?.focus()
  }, [open, step])

  if (!open || !current) return null

  const PAD = 8
  const box = rect
    ? {
        top: Math.max(0, rect.top - PAD),
        left: Math.max(0, rect.left - PAD),
        width: rect.width + PAD * 2,
        height: rect.height + PAD * 2,
      }
    : null

  // Card sits under the spotlight, flipped above when there is no room,
  // horizontally clamped to the viewport.
  const CARD_W = 330
  const cardTop = box
    ? box.top + box.height + 12 + 180 > window.innerHeight
      ? Math.max(12, box.top - 12 - 200)
      : box.top + box.height + 12
    : window.innerHeight / 2 - 120
  const cardLeft = box
    ? Math.min(Math.max(12, box.left), window.innerWidth - CARD_W - 12)
    : window.innerWidth / 2 - CARD_W / 2

  return (
    <div className="fixed inset-0 z-[120]" role="dialog" aria-modal="true" aria-label={t(language, 'tourTitle')}>
      {/* Dimmer; the spotlight is a box-shadow hole around the target box.
          pointer-events-none lets users actually click the highlighted UI.
          The box itself must stay TRANSPARENT (the giant shadow dims everything
          around it); bg only applies in the no-target fallback. */}
      <div
        className="absolute inset-0 bg-navy-950/70 pointer-events-none"
        style={
          box
            ? {
                backgroundColor: 'transparent',
                boxShadow: `0 0 0 9999px rgba(2,6,23,0.72)`,
                top: box.top,
                left: box.left,
                width: box.width,
                height: box.height,
                borderRadius: 16,
              }
            : undefined
        }
      />

      {/* Step card */}
      <div
        className="absolute bg-navy-900 border border-sky/50 rounded-2xl p-4 shadow-2xl transition-all duration-300"
        style={{ top: cardTop, left: cardLeft, width: CARD_W }}
      >
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className="text-[10px] uppercase tracking-wide text-sky font-bold">
            {t(language, 'tourStepLabel')} {step + 1}/{total}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 text-[13px] leading-none px-1"
            aria-label={t(language, 'tourSkip')}
          >
            ✕
          </button>
        </div>
        <h3 className="font-display text-[15px] m-0 mb-1 text-slate-100">{t(language, current.titleKey)}</h3>
        <p className="text-[12px] text-slate-300 m-0 mb-3 leading-relaxed">{t(language, current.bodyKey)}</p>

        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1" aria-hidden="true">
            {TOUR_STEPS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                tabIndex={-1}
                onClick={() => onStepChange(i)}
                className={`w-1.5 h-1.5 rounded-full border-none p-0 transition ${i === step ? 'bg-sky scale-125' : 'bg-slate-600'}`}
              />
            ))}
          </div>
          <div className="flex gap-1.5">
            {step > 0 && (
              <button
                type="button"
                onClick={() => onStepChange(step - 1)}
                className="px-3 py-1.5 rounded-full text-[11.5px] bg-navy-700 border border-border text-slate-200 hover:border-sky transition"
              >
                {t(language, 'tourBack')}
              </button>
            )}
            <button
              ref={nextRef}
              type="button"
              onClick={() => (isLast ? onClose() : onStepChange(step + 1))}
              className="px-3.5 py-1.5 rounded-full text-[11.5px] font-semibold bg-sky text-navy-950 hover:brightness-110 transition"
            >
              {isLast ? t(language, 'tourDone') : t(language, 'tourNext')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
