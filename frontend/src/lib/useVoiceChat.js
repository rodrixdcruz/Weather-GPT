import { useCallback, useEffect, useRef, useState } from 'react'

// Devanagari detection: Hindi/Marathi speech is transcribed in Devanagari
// even when the recognizer was configured for English (and vice versa),
// so the transcript itself tells us what language the user actually spoke.
const DEVANAGARI_RE = /[\u0900-\u097F]/

/**
 * Guess a speechCode from a raw mic transcript.
 * Returns one of 'en-IN' | 'hi-IN' | 'mr-IN'.
 *
 * Devanagari wins over any Latin text (Hindi/Marathi mix liberally with
 * English words like "weather"), and Marathi keywords disambiguate from
 * Chrome's English "mr" transcript. Everything else is treated as English.
 */
export function detectSpeechLanguage(transcript = '') {
  if (!transcript || !transcript.trim()) return 'en-IN'
  if (DEVANAGARI_RE.test(transcript)) {
    const marathiHints = ['आहे', 'का', 'मी', 'तुम्ही', 'काय', 'पाऊस', 'हवामान', 'शेत', 'प्रवास']
    if (marathiHints.some((w) => transcript.includes(w))) return 'mr-IN'
    return 'hi-IN'
  }
  // Chrome often transcribes "mr" for Marathi speech even when the recognizer
  // is set to en-IN, and bare "hi" is a Hindi marker from en-IN recognizers.
  if (/\b(mr|hi)\b/i.test(transcript)) return 'mr-IN'
  return 'en-IN'
}

// Map SpeechRecognition error names to i18n keys (see i18n/index.js ui.*).
const ERROR_KEYS = {
  'not-allowed': 'micDenied',
  'service-not-allowed': 'micDenied',
  'audio-capture': 'micNotFound',
  'network': 'micNetwork',
}

/**
 * Wraps the browser's SpeechRecognition (speech-to-text) and
 * speechSynthesis (text-to-speech) behind one hook. Returns 'idle' |
 * 'listening' | 'speaking' so a UI character can react to it.
 *
 * `speechLang` fixes the recognizer language; pass `autoDetect` to let
 * the mic accept ANY of the app's languages in one press — the transcript
 * is then script/keyword-checked and normalized to a concrete speechCode.
 */
export function useVoiceChat(speechLang = 'en-IN', { autoDetect = false } = {}) {
  const [voiceState, setVoiceState] = useState('idle')
  const [supported] = useState(() => {
    if (typeof window === 'undefined') return false
    // Web Speech needs a secure context. Opening the app over plain http://
    // on a LAN IP (the usual "local server" case) silently kills the mic:
    // recognition.start() throws or errors immediately. localhost is exempt.
    const secure =
      window.isSecureContext ||
      location.hostname === 'localhost' ||
      location.hostname === '127.0.0.1' ||
      location.hostname === '[::1]'
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition) && secure
  })
  const recognitionRef = useRef(null)
  const handlersRef = useRef(null)
  // Some Chrome builds keep recognitionRef.current stale in onresult after a
  // quick stop/start toggle; resolve the session through a generation number.
  const generationRef = useRef(0)
  // Chrome's speechSynthesis.speak() silently no-ops unless speak is called
  // from a real user gesture; prime the engine once on first interaction.
  const primedRef = useRef(false)
  const primeSpeak = useCallback(() => {
    if (primedRef.current || typeof window === 'undefined' || !window.speechSynthesis) return
    primedRef.current = true
    try {
      const u = new SpeechSynthesisUtterance(' ')
      u.volume = 0
      window.speechSynthesis.speak(u)
    } catch {
      /* priming is best-effort */
    }
  }, [])

  useEffect(() => () => recognitionRef.current?.abort(), [])

  const listen = useCallback(
    (onResult, lang = speechLang) => {
      primeSpeak()
      if (!supported) return
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {
          /* already dead */
        }
      }
      const generation = ++generationRef.current

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      const recognition = new SpeechRecognition()
      recognition.lang = autoDetect ? 'en-IN' : lang
      recognition.interimResults = false
      recognition.maxAlternatives = 1

      const settle = () => {
        recognitionRef.current = null
        if (generationRef.current === generation) setVoiceState('idle')
        else setVoiceState((s) => (s === 'listening' ? 'idle' : s))
      }
      recognition.onstart = () => {
        if (generationRef.current === generation) setVoiceState('listening')
      }
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript || ''
        const detected = autoDetect ? detectSpeechLanguage(transcript) : lang
        handlersRef.current?.(transcript, { detectedLang: detected })
      }
      recognition.onerror = (event) => {
        const key = ERROR_KEYS[event.error] || 'micError'
        handlersRef.current?.(null, { micError: key })
      }
      recognition.onend = settle

      recognitionRef.current = recognition
      handlersRef.current = onResult
      try {
        recognition.start()
      } catch {
        // start() can throw synchronously (e.g. InvalidStateError on
        // rapid re-press); treat it like an immediate failure.
        settle()
      }
    },
    [supported, speechLang, autoDetect, primeSpeak],
  )

  const stopListening = useCallback(() => {
    ++generationRef.current
    try {
      recognitionRef.current?.stop()
    } catch {
      /* already dead */
    }
    recognitionRef.current = null
    setVoiceState('idle')
  }, [])

  const speak = useCallback(
    (text, lang = speechLang) => {
      primeSpeak()
      if (typeof window === 'undefined' || !window.speechSynthesis) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = lang
      utterance.onstart = () => setVoiceState('speaking')
      utterance.onend = () => setVoiceState('idle')
      utterance.onerror = () => setVoiceState('idle')
      window.speechSynthesis.speak(utterance)
    },
    [speechLang, primeSpeak],
  )

  return { voiceState, supported, listen, stopListening, speak, detectSpeechLanguage }
}
