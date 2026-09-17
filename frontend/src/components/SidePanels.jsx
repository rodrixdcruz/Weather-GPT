import { t } from '../i18n'

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

/**
 * Opens a ready-made navigation route from the user's live position to a
 * shelter. Uses Google Maps' universal dir URL — no API key, and on phones
 * it hands off to the installed Maps app with turn-by-turn navigation.
 */
export function DirectionsLink({ from, to, name, language = 'en', className }) {
  if (
    !from || !Number.isFinite(from.latitude) || !Number.isFinite(from.longitude) ||
    !to || !Number.isFinite(to.latitude) || !Number.isFinite(to.longitude)
  ) return null
  const fmt = (v) => v.toFixed(6)
  const url =
    `https://www.google.com/maps/dir/?api=1` +
    `&origin=${fmt(from.latitude)},${fmt(from.longitude)}` +
    `&destination=${fmt(to.latitude)},${fmt(to.longitude)}` +
    `&travelmode=driving`
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${t(language, 'directionsAria')} ${name}`}
      className={className}
    >
      ➤ {t(language, 'directions')}
    </a>
  )
}

export function SafeZonesList({ zones = [], origin = null, language = 'en' }) {
  return (
    <div className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4">
      <div className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold mb-2">
        {t(language, 'verifiedShelters')}
      </div>
      <div className="flex flex-col gap-2">
        {zones.map((z) => (
          <div key={z.name} className="flex items-center justify-between gap-2 bg-navy-700 rounded-lg px-3 py-2">
            <div className="min-w-0">
              <div className="text-[13px] truncate">{z.name}</div>
              <div className="text-[10.5px] text-slate-300">{z.distance_km} {t(language, 'km')}</div>
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
                language={language}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded bg-sky/15 text-sky border border-sky/40 hover:bg-sky/25 transition-colors whitespace-nowrap"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
