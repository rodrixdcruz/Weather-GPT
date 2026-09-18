import { useEffect, useState } from 'react'
import { t } from '../i18n'
import { fetchTravelTimes } from '../lib/routing'

// Tip copy per language per scenario. Falls back to English if a
// language/scenario pair is missing.
const TIPS = {
  en: {
    normal: ['Stay hydrated and check the forecast before long trips.', 'Keep an emergency contact list handy just in case.', 'Follow official weather updates for your area.'],
    heavy_rainfall: ['Avoid walking or driving through flooded roads.', 'Keep electronics and documents in waterproof bags.', 'Stay away from low-lying areas and drains.'],
    heatwave: ['Avoid outdoor activity between 12–4pm.', 'Drink water regularly even if not thirsty.', 'Watch for signs of heat exhaustion in elderly and children.'],
    thunderstorm: ['Stay indoors and avoid open fields or tall isolated trees.', 'Unplug sensitive electronics during lightning.', 'Avoid using landline phones during a storm.'],
    flood_risk: ['Move valuables and documents to higher shelves.', 'Be ready to evacuate if authorities advise it.', 'Avoid contact with flood water — it may be contaminated.'],
  },
  hi: {
    normal: ['हाइड्रेटेड रहें और लंबी यात्रा से पहले पूर्वानुमान देखें।', 'आपातकालीन संपर्क सूची तैयार रखें।', 'अपने क्षेत्र के आधिकारिक मौसम अपडेट का पालन करें।'],
    heavy_rainfall: ['जलभराव वाली सड़कों से गाड़ी चलाने या चलने से बचें।', 'इलेक्ट्रॉनिक्स और दस्तावेज़ वाटरप्रूफ बैग में रखें।', 'निचले इलाकों और नालियों से दूर रहें।'],
    heatwave: ['दोपहर 12–4 बजे के बीच बाहरी गतिविधि से बचें।', 'प्यास न लगे तब भी नियमित रूप से पानी पिएं।', 'बुजुर्गों और बच्चों में लू के लक्षणों पर ध्यान दें।'],
    thunderstorm: ['घर के अंदर रहें, खुले मैदान या अकेले ऊँचे पेड़ों से बचें।', 'बिजली गिरने के दौरान संवेदनशील इलेक्ट्रॉनिक्स अनप्लग करें।', 'तूफान के दौरान लैंडलाइन फोन का उपयोग न करें।'],
    flood_risk: ['कीमती सामान और दस्तावेज़ ऊंची जगह पर रखें।', 'अधिकारियों की सलाह पर निकलने के लिए तैयार रहें।', 'बाढ़ के पानी के संपर्क से बचें — यह दूषित हो सकता है।'],
  },
  mr: {
    normal: ['हायड्रेटेड रहा आणि लांबच्या प्रवासापूर्वी अंदाज तपासा.', 'आणीबाणी संपर्क यादी तयार ठेवा.', 'तुमच्या भागातील अधिकृत हवामान अपडेट्सचे अनुसरण करा.'],
    heavy_rainfall: ['पूरग्रस्त रस्त्यांवरून चालणे किंवा गाडी चालवणे टाळा.', 'इलेक्ट्रॉनिक्स आणि कागदपत्रे वॉटरप्रूफ बॅगमध्ये ठेवा.', 'सखल भाग आणि गटारांपासून दूर रहा.'],
    heatwave: ['दुपारी 12–4 दरम्यान बाहेरील क्रियाकलाप टाळा.', 'तहान नसली तरी नियमितपणे पाणी प्या.', 'वृद्ध आणि मुलांमध्ये उष्माघाताच्या लक्षणांकडे लक्ष द्या.'],
    thunderstorm: ['घरातच रहा, मोकळी मैदाने किंवा एकटी उंच झाडे टाळा.', 'विजांच्या वेळी संवेदनशील इलेक्ट्रॉनिक्स अनप्लग करा.', 'वादळादरम्यान लँडलाइन फोन वापरणे टाळा.'],
    flood_risk: ['मौल्यवान वस्तू व कागदपत्रे उंच जागी हलवा.', 'अधिकाऱ्यांनी सांगितल्यास स्थलांतर करण्यास तयार रहा.', 'पुराच्या पाण्याशी संपर्क टाळा — ते दूषित असू शकते.'],
  },
}

export function SafetyTips({ scenario, language = 'en' }) {
  const tips = TIPS[language]?.[scenario] || TIPS.en[scenario] || TIPS.en.normal
  return (
    <div className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold mb-2">{t(language, 'safetyTips')}</div>
      <div className="flex flex-col gap-2">
        {tips.map((tip, i) => (
          <div key={i} className="flex gap-2.5 text-[13px] leading-relaxed">
            <span className="font-mono text-sky flex-shrink-0">0{i + 1}</span>
            <span>{tip}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const TRAVEL_MODES = ['walking', 'driving']

/**
 * Walking/driving segmented control for the shelter directions. One shared
 * instance per surface (list header, map overlay) so the choice follows the
 * user across both — in an emergency most shelters are reached on foot.
 */
export function TravelModeToggle({ mode = 'driving', onChange, language = 'en' }) {
  return (
    <div
      role="group"
      aria-label={t(language, 'travelMode')}
      className="inline-flex items-center bg-navy-950/85 border border-border rounded-full p-0.5 divide-x divide-border"
    >
      {TRAVEL_MODES.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange?.(m)}
          aria-pressed={mode === m}
          className={`px-2.5 py-1 text-[10.5px] font-semibold rounded-full transition-colors ${
            mode === m ? 'bg-sky/25 text-sky' : 'text-slate-300 hover:text-slate-100'
          }`}
        >
          {m === 'walking' ? '🚶 ' : '🚗 '}
          {t(language, m)}
        </button>
      ))}
    </div>
  )
}

/**
 * Builds Google Maps' universal dir URL — the turn-by-turn handoff used by
 * DirectionsLink. Kept separate so the in-app route panel can offer the same
 * deep link without duplicating the format (6-decimal coords, ~11 cm).
 */
export function mapsDirectionsUrl(from, to, mode = 'driving') {
  const fmt = (v) => Number(v).toFixed(6)
  const travelmode = mode === 'walking' ? 'walking' : 'driving'
  return (
    `https://www.google.com/maps/dir/?api=1` +
    `&origin=${fmt(from.latitude)},${fmt(from.longitude)}` +
    `&destination=${fmt(to.latitude)},${fmt(to.longitude)}` +
    `&travelmode=${travelmode}`
  )
}

/** Compact 🚶/🚗 minute badges under a shelter's straight-line distance. */
function TravelTimeBadges({ times, language }) {
  if (!times) return null
  const badge = (icon, min) => (
    <span
      key={icon}
      className="inline-flex items-center gap-0.5 ml-2 text-[10px] text-slate-100 bg-navy-900/70 border border-border rounded px-1 py-px"
      title={t(language, 'travelTimes')}
    >
      {icon}
      {min == null ? t(language, 'timesUnavailable') : `${min} ${t(language, 'routeMinutes')}`}
    </span>
  )
  return (
    <span>
      {badge(t(language, 'walkTime'), times.walkMin)}
      {badge(t(language, 'driveTime'), times.driveMin)}
    </span>
  )
}

/**
 * Opens a ready-made navigation route from the user's live position to a
 * shelter. Uses Google Maps' universal dir URL — no API key, and on phones
 * it hands off to the installed Maps app with turn-by-turn navigation.
 * `mode` is 'driving' (default) or 'walking'; anything else falls back to
 * driving so a stray value can never produce a broken Maps URL.
 */
export function DirectionsLink({ from, to, name, mode = 'driving', language = 'en', className, onDirections }) {
  if (
    !from || !Number.isFinite(from.latitude) || !Number.isFinite(from.longitude) ||
    !to || !Number.isFinite(to.latitude) || !Number.isFinite(to.longitude)
  ) return null
  const content = (
    <>
      ➤ {t(language, 'directions')}
    </>
  )
  // With `onDirections` the click opens the route inside the app's map; the
  // Google Maps handoff stays available via the browser context menu.
  if (onDirections) {
    return (
      <button
        type="button"
        title={`${t(language, 'directionsAria')} ${name}`}
        onClick={() => onDirections(to, name)}
        className={className}
      >
        {content}
      </button>
    )
  }
  return (
    <a href={mapsDirectionsUrl(from, to, mode)} target="_blank" rel="noopener noreferrer" title={`${t(language, 'directionsAria')} ${name}`} className={className}>
      {content}
    </a>
  )
}

/**
 * Fetches walk + drive time estimates (OSRM table, one request per mode)
 * from the live origin to all shelters. Returns an array aligned with
 * `zones`: `{ walkMin, driveMin }` or null while loading/unavailable.
 * Re-runs when the origin moves; a stale response is ignored via abort.
 */
function useTravelTimes(zones, origin, enabled) {
  const [times, setTimes] = useState([])
  useEffect(() => {
    if (!enabled || !origin || !zones.length) {
      setTimes([])
      return
    }
    const controller = new AbortController()
    // Match the list's [name] keying: times are positional.
    const load = async (mode) => {
      try {
        return await fetchTravelTimes(origin, zones, mode, { signal: controller.signal })
      } catch {
        return null // per-mode failure degrades to '—', never blocks the other
      }
    }
    Promise.all([load('walking'), load('driving')]).then(([walk, drive]) => {
      if (controller.signal.aborted) return
      setTimes(zones.map((_, i) => ({ walkMin: walk?.[i] ?? null, driveMin: drive?.[i] ?? null })))
    })
    return () => controller.abort()
    // `enabled` only gates the early return above; origin/zones drive the fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [origin, zones])
  return times
}

export function SafeZonesList({ zones = [], origin = null, travelMode = 'driving', onTravelModeChange, onDirections, language = 'en' }) {
  const times = useTravelTimes(zones, origin, Boolean(origin))

  // Rank by the CURRENT travel mode's time: fastest first, unknown times
  // last (distance as tiebreaker). Each row keeps its original index so the
  // positional `times` entries stay aligned after sorting. While times are
  // loading/unavailable every entry is null and the order falls back to the
  // backend's distance sort — identical to the pre-times behavior.
  const timeKey = travelMode === 'walking' ? 'walkMin' : 'driveMin'
  const rows = zones
    .map((z, i) => ({ zone: z, time: times[i]?.[timeKey] ?? null, index: i }))
    .sort((a, b) => {
      if (a.time == null && b.time == null) return a.zone.distance_km - b.zone.distance_km
      if (a.time == null) return 1
      if (b.time == null) return -1
      return a.time - b.time || a.zone.distance_km - b.zone.distance_km
    })
  // First row with a known time = fastest overall for this mode. Only that
  // row gets the badge + highlight; without any times nothing is highlighted.
  const fastestIndex = rows.find((r) => r.time != null)?.index

  return (
    <div data-tour="shelter-list" className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold">
          {t(language, 'verifiedShelters')}
        </div>
        <TravelModeToggle mode={travelMode} onChange={onTravelModeChange} language={language} />
      </div>
      <div className="flex flex-col gap-2">
        {rows.map(({ zone: z, index: i }) => (
          <div
            key={z.name}
            className={`flex items-center justify-between gap-2 bg-navy-700 rounded-lg px-3 py-2 ${
              i === fastestIndex ? 'ring-1 ring-emerald-500/50' : ''
            }`}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[13px] truncate">{z.name}</span>
                {i === fastestIndex && (
                  <span
                    className="text-[9px] px-1.5 py-px rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 whitespace-nowrap flex-shrink-0"
                    title={`${t(language, 'fastest')} · ${t(language, travelMode)}`}
                  >
                    ⚡ {t(language, 'fastest')}
                  </span>
                )}
              </div>
              <div className="text-[10.5px] text-slate-300">
                {z.distance_km} {t(language, 'km')}
                <TravelTimeBadges times={times[i]} language={language} />
              </div>
            </div>
            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
              <span
                className={`text-[9.5px] px-2 py-0.5 rounded border ${
                  z.is_verified
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
                }`}
              >
                {z.is_verified ? t(language, 'verified') : t(language, 'estimate')}
              </span>
              <DirectionsLink
                from={origin}
                to={z}
                name={z.name}
                mode={travelMode}
                language={language}
                onDirections={onDirections}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded bg-sky/15 text-sky border border-sky/40 hover:bg-sky/25 transition-colors whitespace-nowrap"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
