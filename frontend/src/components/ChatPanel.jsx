import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { I18N, t } from '../i18n'
import { useVoiceChat } from '../lib/useVoiceChat'
import { getWeatherProp } from '../weather/ui-state'
import { useRiskTrend } from '../lib/useRiskTrend'
import VoiceCharacter from './VoiceCharacter'

// The WebGL presenter (three.js) is heavy, so it loads on demand; the 2D SVG
// mascot shows while the chunk downloads and stays as the WebGL fallback.
const Presenter3D = lazy(() => import('./Presenter3D'))

export default function ChatPanel({
  language,
  latitude,
  longitude,
  scenario,
  role = 'customer',
  weather = null,
  riskLevel = null,
}) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [voiceMode, setVoiceMode] = useState(false)
  const sessionId = useRef(`session-${Date.now()}`)
  const bodyRef = useRef(null)
  // A voice transcript that lands while the previous answer is still loading
  // is queued here instead of being silently dropped.
  const pendingSendRef = useRef(null)
  const speechLang = I18N[language].speechCode

  // Mic auto-detects the spoken language (en/hi/mr) per turn instead of
  // being locked to the UI language; the reply is requested and spoken in
  // whatever language was actually spoken.
  const { voiceState, supported, listen, stopListening, speak } = useVoiceChat(speechLang, { autoDetect: true })

  // Reset the conversation when the language changes (greeting is localized)
  // or the role changes (suggestions + interpretation are role-aware).
  useEffect(() => {
    setMessages([{ role: 'assistant', content: I18N[language].greet, key: `greet-${language}-${role}` }])
  }, [language, role])

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages])

  async function send(text, { spoken = false, detectedLang = null } = {}) {
    if (!text.trim()) return
    if (sending) {
      pendingSendRef.current = { text, opts: { spoken, detectedLang } }
      return
    }
    // Language for THIS turn: mic-detected when voice was used, otherwise
    // the UI-selected language. Only the base code goes to the backend
    // (it normalizes anyway); the full code drives speech synthesis.
    const turnSpeechLang = detectedLang || speechLang
    const turnLang = turnSpeechLang.split('-')[0]
    setMessages((m) => [...m, { role: 'user', content: text, detectedLang: detectedLang || null }])
    setInput('')
    setSending(true)
    try {
      const res = await api.sendChatMessage({
        message: text,
        sessionId: sessionId.current,
        language: turnLang,
        latitude,
        longitude,
        scenario,
        role,
      })
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.reply, dataUsed: res.data_used, fallbackUsed: res.fallback_used, sources: res.sources },
      ])
      // Speak the reply back only if this turn started as voice input,
      // so typed conversations stay silent — in the detected language.
      if (spoken || voiceMode) speak(res.reply, turnSpeechLang)
    } catch {
      const fallback = t(language, 'chatError')
      setMessages((m) => [...m, { role: 'assistant', content: fallback, isError: true }])
    } finally {
      setSending(false)
      if (pendingSendRef.current) {
        const next = pendingSendRef.current
        pendingSendRef.current = null
        send(next.text, next.opts)
      }
    }
  }

  function handleMicClick() {
    // Second tap while listening stops the mic instead of spawning a second,
    // conflicting recognition session (which made the mic seem to "close").
    if (voiceState === 'listening') {
      stopListening()
      return
    }
    if (!supported) {
      setMessages((m) => [...m, { role: 'assistant', content: t(language, 'voiceUnsupported') }])
      return
    }
    setVoiceMode(true)
    listen((transcript, meta) => {
      // The hook reports mic failures (denied permission, no device, network)
      // through this callback — show them instead of failing silently.
      if (meta?.micError) {
        setMessages((m) => [...m, { role: 'assistant', content: t(language, meta.micError), isError: true }])
        return
      }
      send(transcript, { spoken: true, detectedLang: meta?.detectedLang || null })
    }, speechLang)
  }

  // Avatar reacts to more than the mic: while a reply is loading the mascot
  // switches to its 'thinking' pose instead of standing idle.
  const avatarState = voiceState !== 'idle' ? voiceState : sending ? 'thinking' : 'idle'
  // Short-lived reaction to the overall risk level changing: the mascot
  // celebrates a drop and looks concerned about a rise.
  const riskTrend = useRiskTrend(riskLevel)
  // Status line glows in the avatar's state color so the change is noticeable;
  // a risk-trend reaction takes visual precedence while its burst lasts.
  const AVATAR_COLOR = { idle: null, listening: '#22c55e', thinking: '#a78bfa', speaking: '#f59e0b' }
  const statusColor =
    riskTrend === 'improved' ? '#22c55e' : riskTrend === 'worsened' ? '#f97316' : AVATAR_COLOR[avatarState]
  // The presenter holds up a prop matching the live weather: umbrella in rain,
  // sun-shade card in heat/sun, plain info card otherwise (null before load).
  const weatherProp = getWeatherProp(weather)

  // Role-aware starter questions in the selected language (falls back to
  // the customer set when a role has no localized suggestions).
  const dict = I18N[language] || I18N.en
  const roleSuggestions = dict.suggestionsByRole || {}
  const suggestions = roleSuggestions[role] || dict.chips || roleSuggestions.customer || []

  return (
    <div data-tour="chat" className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl overflow-hidden flex flex-col p-0">
      <div className="px-4 py-3 border-b border-border flex items-center gap-3">
        <Suspense fallback={<VoiceCharacter state={avatarState} size={52} weatherProp={weatherProp} mood={riskTrend} />}>
          <Presenter3D
            state={avatarState}
            size={72}
            weatherProp={weatherProp}
            mood={riskTrend}
            hint={t(language, 'dragToRotate')}
          />
        </Suspense>
        <div>
          <div className="font-semibold text-sm">{t(language, 'assistantTitle')}</div>
          <div
            className="text-[10.5px] font-medium transition-colors"
            style={statusColor ? { color: statusColor } : undefined}
          >
            {voiceState === 'listening'
              ? t(language, 'listening')
              : riskTrend === 'improved'
              ? '🎉 ' + t(language, 'riskImproved')
              : riskTrend === 'worsened'
              ? '⚠️ ' + t(language, 'riskWorsened')
              : avatarState === 'thinking'
              ? '💭 ' + t(language, 'typing')
              : voiceState === 'speaking'
              ? '🔊 ' + t(language, 'assistantTitle')
              : t(language, 'assistantSub')}
          </div>
        </div>
      </div>

      <div ref={bodyRef} className="h-[340px] overflow-y-auto px-4 py-3.5 flex flex-col gap-2.5">
        {messages.map((m, i) => (
          <div
            key={`${m.key || 'msg'}-${i}`}
            className={`max-w-[85%] px-3 py-2.5 rounded-xl text-[13px] leading-relaxed ${
              m.role === 'user' ? 'self-end bg-sky/20 text-slate-100' : 'self-start bg-navy-700 text-slate-100'
            }`}
          >
            {m.fallbackUsed && (
              <div className="text-[10px] text-yellow-400 border border-yellow-500/30 bg-yellow-500/10 rounded px-1.5 py-0.5 inline-block mb-1.5">
                ⚡ {t(language, 'aiUnavailableNotice')}
              </div>
            )}
            <div>{m.content}</div>
            {m.role === 'user' && m.detectedLang && (
              <div className="text-[9.5px] text-slate-400 text-right mt-0.5">
                🎙 {(I18N[m.detectedLang.split('-')[0]] || {}).name || m.detectedLang}
              </div>
            )}
            {m.sources?.length > 0 && (
              <div className="text-[10px] text-slate-300 mt-1.5 flex flex-wrap gap-1">
                <span>📚 {t(language, 'sources')}:</span>
                {m.sources.map((s) => (
                  <span key={s} className="bg-navy-800 border border-border rounded px-1.5 py-0.5">{s}</span>
                ))}
              </div>
            )}
            {m.dataUsed && (
              <div className="text-[10px] text-slate-300 mt-1.5">
                📊 {m.dataUsed.rainfall_mm}mm · {m.dataUsed.precip_probability_pct}% · {m.dataUsed.risk_level} · {m.dataUsed.source}
                {m.dataUsed.is_verified ? ' ✓' : ''}
              </div>
            )}
          </div>
        ))}
        {sending && <div className="self-start text-[12px] text-slate-300">{t(language, 'typing')}</div>}
      </div>

      <div className="flex flex-wrap gap-1.5 px-4 pb-2.5">
        {suggestions.map((c) => (
          <button
            key={c}
            className="text-[11.5px] bg-navy-700 border border-border rounded-full px-2.5 py-1 hover:border-sky transition"
            onClick={() => send(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 px-4 py-3 border-t border-border">
        <button
          className={`w-9 h-9 rounded-full border flex items-center justify-center flex-shrink-0 transition ${
            voiceState === 'listening'
              ? 'bg-emerald-500/20 border-emerald-500 animate-pulse'
              : 'bg-navy-700 border-border hover:border-sky'
          }`}
          onClick={handleMicClick}
          title={t(language, 'speakNow')}
        >
          🎤
        </button>
        <input
          className="flex-1 bg-navy-700 border border-border rounded-full px-3.5 py-2 text-[13px] outline-none focus:border-sky"
          placeholder={voiceState === 'listening' ? t(language, 'listening') : I18N[language].placeholder}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(input)}
        />
        <button
          className="bg-sky text-navy-950 font-semibold text-xs px-4 py-2 rounded-full disabled:opacity-50"
          onClick={() => send(input)}
          disabled={sending}
        >
          {t(language, 'send')}
        </button>
      </div>
    </div>
  )
}
