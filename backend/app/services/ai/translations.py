"""
Language support for AI-generated chat text.

The AI contract (services/ai/base.py) requires every reply to be in the
language the client requested. LLM providers get an explicit instruction
(see `language_prompt_clause`); the deterministic mock provider and the
router's AI-unavailable fallback use the template tables below, because
neither of them can lean on a model to translate.

Supported codes mirror the frontend i18n dictionary (frontend/src/i18n):
English (en), Hindi (hi) and Marathi (mr). Anything else — missing,
empty, or unsupported — degrades to English instead of erroring.
"""

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = frozenset({"en", "hi", "mr"})

# (name in English, native name). LLM prompts use both: small local
# models follow a spoken language name far more reliably than a bare
# BCP-47 code like "hi".
LANGUAGE_NAMES = {
    "en": ("English", "English"),
    "hi": ("Hindi", "हिन्दी"),
    "mr": ("Marathi", "मराठी"),
}

# Risk-level display words (the frontend shows the same words via i18n).
RISK_LEVELS = {
    "hi": {"low": "कम", "moderate": "मध्यम", "high": "उच्च", "extreme": "अत्यधिक"},
    "mr": {"low": "कमी", "moderate": "मध्यम", "high": "उच्च", "extreme": "अत्यंत"},
}

# Weather conditions arrive in English (WMO descriptions from the weather
# providers, plus the mock demo scenarios). Unknown strings are returned
# unchanged rather than dropped, so a missing entry degrades to English
# for that word while the rest of the reply stays localized.
CONDITIONS = {
    "hi": {
        "Clear sky": "साफ़ आसमान",
        "Mainly clear": "ज़्यादातर साफ़",
        "Partly cloudy": "आंशिक रूप से बादल",
        "Overcast": "बादल छाए हुए",
        "Fog": "कोहरा",
        "Freezing fog": "जमने वाला कोहरा",
        "Freezing fog — icy surfaces possible": "जमने वाला कोहरा — सतहें बर्फ़ीली हो सकती हैं",
        "Light drizzle": "हल्की बूंदाबांदी",
        "Drizzle": "बूंदाबांदी",
        "Dense drizzle": "तेज़ बूंदाबांदी",
        "Freezing drizzle": "जमने वाली बूंदाबांदी",
        "Freezing drizzle — icy surfaces possible": "जमने वाली बूंदाबांदी — सतहें बर्फ़ीली हो सकती हैं",
        "Dense freezing drizzle": "तेज़ जमने वाली बूंदाबांदी",
        "Dense freezing drizzle — icy surfaces possible": "तेज़ जमने वाली बूंदाबांदी — सतहें बर्फ़ीली हो सकती हैं",
        "Light rain": "हल्की बारिश",
        "Rain": "बारिश",
        "Heavy rain": "भारी बारिश",
        "Freezing rain": "जमने वाली बारिश",
        "Freezing rain — icy surfaces possible": "जमने वाली बारिश — सतहें बर्फ़ीली हो सकती हैं",
        "Heavy freezing rain": "तेज़ जमने वाली बारिश",
        "Heavy freezing rain — icy surfaces possible": "तेज़ जमने वाली बारिश — सतहें बर्फ़ीली हो सकती हैं",
        "Light snow": "हल्की बर्फ़बारी",
        "Snow": "बर्फ़बारी",
        "Heavy snow": "भारी बर्फ़बारी",
        "Snow grains": "बर्फ़ के कण",
        "Light showers": "हल्की बौछारें",
        "Showers": "बौछारें",
        "Violent showers": "बहुत तेज़ बौछारें",
        "Snow showers": "बर्फ़ की बौछारें",
        "Heavy snow showers": "भारी बर्फ़ की बौछारें",
        "Thunderstorm": "आंधी-तूफ़ान",
        "Thunderstorm w/ hail": "ओलों के साथ आंधी-तूफ़ान",
        "Thunderstorm with heavy hail": "भारी ओलों के साथ आंधी-तूफ़ान",
        "Unknown conditions": "अज्ञात स्थिति",
        # Mock demo scenarios (services/weather/mock_provider.py)
        "Clear, extreme heat": "साफ़ आसमान, अत्यधिक गर्मी",
        "Persistent heavy rain": "लगातार भारी बारिश",
        "Hazy smog": "धुंधली स्मॉग",
    },
    "mr": {
        "Clear sky": "निर्भेळ आकाश",
        "Mainly clear": "बहुतेक निर्भेळ",
        "Partly cloudy": "अंशतः ढगाळ",
        "Overcast": "संपूर्ण ढगाळ",
        "Fog": "धुके",
        "Freezing fog": "गोठणारे धुके",
        "Freezing fog — icy surfaces possible": "गोठणारे धुके — पृष्ठभाग बरफाळ होऊ शकतात",
        "Light drizzle": "हलकी झुंबर",
        "Drizzle": "झुंबर",
        "Dense drizzle": "जोरात झुंबर",
        "Freezing drizzle": "गोठणारी झुंबर",
        "Freezing drizzle — icy surfaces possible": "गोठणारी झुंबर — पृष्ठभाग बरफाळ होऊ शकतात",
        "Dense freezing drizzle": "जोरात गोठणारी झुंबर",
        "Dense freezing drizzle — icy surfaces possible": "जोरात गोठणारी झुंबर — पृष्ठभाग बरफाळ होऊ शकतात",
        "Light rain": "हलका पाऊस",
        "Rain": "पाऊस",
        "Heavy rain": "मुसळधार पाऊस",
        "Freezing rain": "गोठणारा पाऊस",
        "Freezing rain — icy surfaces possible": "गोठणारा पाऊस — पृष्ठभाग बरफाळ होऊ शकतात",
        "Heavy freezing rain": "जोरात गोठणारा पाऊस",
        "Heavy freezing rain — icy surfaces possible": "जोरात गोठणारा पाऊस — पृष्ठभाग बरफाळ होऊ शकतात",
        "Light snow": "हलकी बरफवृष्टी",
        "Snow": "बरफवृष्टी",
        "Heavy snow": "मोठी बरफवृष्टी",
        "Snow grains": "बरफाचे कण",
        "Light showers": "हलक्या सऱ्या",
        "Showers": "सऱ्या",
        "Violent showers": "प्रचंड सऱ्या",
        "Snow showers": "बरफाच्या सऱ्या",
        "Heavy snow showers": "जोरात बरफाच्या सऱ्या",
        "Thunderstorm": "वादळी पाऊस",
        "Thunderstorm w/ hail": "गारांसह वादळी पाऊस",
        "Thunderstorm with heavy hail": "मोठ्या गारांसह वादळी पाऊस",
        "Unknown conditions": "अज्ञात स्थिती",
        # Mock demo scenarios (services/weather/mock_provider.py)
        "Clear, extreme heat": "निर्भेळ आकाश, प्रचंड उष्णता",
        "Persistent heavy rain": "सातत्याने मुसळधार पाऊस",
        "Hazy smog": "धुळ्याची कोंदट हवा (स्मॉग)",
    },
}

# Deterministic mock-provider actions, per language and role. "risk" maps
# the 4-level severity taxonomy (Severity enum); "critical" is kept as a
# legacy alias so older callers never fall through to the calm wording.
MOCK_ROLE_ACTIONS = {
    "en": {
        "risk": {
            "low": "Conditions are calm right now — no special precautions needed beyond normal awareness.",
            "moderate": "Keep an eye on updates and avoid non-essential travel through low-lying or flood-prone routes.",
            "high": "Avoid travel through flood-prone or exposed areas, and keep emergency contacts and documents ready.",
            "extreme": "Move to higher ground or a designated safe zone now if you are in a vulnerable area, and follow official evacuation guidance.",
            "critical": "Move to higher ground or a designated safe zone now if you are in a vulnerable area, and follow official evacuation guidance.",
        },
        "farmer": "Plan field work around the wettest and windiest hours, and check drainage before the rain arrives.",
        "traveler": "Allow extra journey time, avoid flooded or exposed routes, and monitor conditions before setting out.",
        "officer": "Monitor official IMD/NDMA channels and pre-position resources where risk is elevated.",
    },
    "hi": {
        "risk": {
            "low": "अभी हालात शांत हैं — सामान्य सतर्कता के अलावा किसी ख़ास सावधानी की ज़रूरत नहीं।",
            "moderate": "अपडेट पर नज़र रखें और निचले इलाक़ों या बाढ़ वाले रास्तों से ग़ैर-ज़रूरी यात्रा टालें।",
            "high": "बाढ़ प्रवण या खुले इलाक़ों से यात्रा टालें, और आपातकालीन संपर्क व दस्तावेज़ तैयार रखें।",
            "extreme": "अगर आप जोखिम वाले इलाक़े में हैं तो अभी ऊँची ज़मीन या तय सुरक्षित स्थान पर जाएँ और आधिकारिक निकासी निर्देशों का पालन करें।",
            "critical": "अगर आप जोखिम वाले इलाक़े में हैं तो अभी ऊँची ज़मीन या तय सुरक्षित स्थान पर जाएँ और आधिकारिक निकासी निर्देशों का पालन करें।",
        },
        "farmer": "खेत का काम सबसे गीले और तेज़ हवा वाले समय से बचाकर करें, और बारिश आने से पहले जल-निकासी जाँच लें।",
        "traveler": "यात्रा में अतिरिक्त समय रखें, बाढ़ वाले या खुले रास्तों से बचें, और निकलने से पहले हालात देख लें।",
        "officer": "आधिकारिक IMD/NDMA चैनलों पर नज़र रखें और जहाँ जोखिम बढ़ा हुआ है वहाँ संसाधन पहले से तैनात करें।",
    },
    "mr": {
        "risk": {
            "low": "सध्या परिस्थिती शांत आहे — सामान्य सतर्कतेव्यतिरिक्त काही विशेष खबरदारीची गरज नाही.",
            "moderate": "अपडेट्सवर लक्ष ठेवा आणि खोलगट भागांतून किंवा पुराच्या शक्यता असलेल्या रस्त्यांवून गरजेशिवाय प्रवास टाळा.",
            "high": "पुराच्या शक्यता असलेल्या किंवा उघड्या भागांतून प्रवास टाळा आणि आपत्कालीन संपर्क व कागदपत्रे तयार ठेवा.",
            "extreme": "तुम्ही धोक्याच्या भागात असाल तर आत्ताच उंच भागात किंवा निश्चित सुरक्षित क्षेत्रात जा आणि अधिकृत निर्वासन सूचनांचे पालन करा.",
            "critical": "तुम्ही धोक्याच्या भागात असाल तर आत्ताच उंच भागात किंवा निश्चित सुरक्षित क्षेत्रात जा आणि अधिकृत निर्वासन सूचनांचे पालन करा.",
        },
        "farmer": "शेतकाम सर्वात ओल्या आणि जोरदार वाऱ्याच्या वेळेपासून दूर नियोजित करा आणि पाऊस यायच्या आधी जल-निचरा तपासा.",
        "traveler": "प्रवासासाठी अतिरिक्त वेळ ठेवा, पुराचे किंवा उघड्या रस्ते टाळा आणि निघण्यापूर्वी परिस्थिती पाहा.",
        "officer": "अधिकृत IMD/NDMA माध्यमांवर लक्ष ठेवा आणि जिथे धोका वाढला आहे तिथे संसाधने आधीच तैनात करा.",
    },
}

# Mock-provider reply templates, per language. Values are pre-formatted
# strings; see MockAIProvider.generate_reply for the exact keys.
MOCK_TEMPLATES = {
    "en": {
        "safety": (
            "For {location}, current risk is {risk_level} ({score}/100). {action} "
            "Tap the SOS button if you need emergency contacts or want to log your location."
        ),
        "rain": (
            "Expected rainfall near {location} is {rainfall}mm with a {rain_chance}% chance of "
            "precipitation, as of {observed_at}. Risk level is {risk_level}. {action}"
        ),
        "heat": (
            "Current temperature near {location} is {temperature}°C with {humidity}% humidity. "
            "Risk level is {risk_level}. {action}"
        ),
        "general": (
            "Here's the latest for {location} as of {observed_at}: {condition}, {temperature}°C, "
            "{rainfall}mm expected rainfall. Overall risk is {risk_level} ({score}/100). {action}"
        ),
        "unverified": " (Note: this reading is a model estimate, not yet confirmed by an official source.)",
    },
    "hi": {
        "safety": (
            "{location} में मौजूदा जोखिम स्तर {risk_level} है ({score}/100)। {action} "
            "आपातकालीन संपर्कों के लिए या अपनी लोकेशन दर्ज कराने के लिए SOS बटन दबाएँ।"
        ),
        "rain": (
            "{location} के आसपास अपेक्षित वर्षा {rainfall} मिमी, बारिश की संभावना {rain_chance}% "
            "({observed_at} तक)। जोखिम स्तर {risk_level} है। {action}"
        ),
        "heat": (
            "{location} के आसपास मौजूदा तापमान {temperature}°C और नमी {humidity}% है। "
            "जोखिम स्तर {risk_level} है। {action}"
        ),
        "general": (
            "{observed_at} तक {location} की ताज़ा जानकारी: {condition}, {temperature}°C, "
            "अपेक्षित वर्षा {rainfall} मिमी। समग्र जोखिम {risk_level} ({score}/100)। {action}"
        ),
        "unverified": " (नोट: यह रीडिंग मॉडल का अनुमान है, अभी किसी आधिकारिक स्रोत से पुष्ट नहीं हुई है।)",
    },
    "mr": {
        "safety": (
            "{location} येथील सध्याचा धोका पातळी {risk_level} आहे ({score}/100). {action} "
            "आपत्कालीन संपर्कांसाठी किंवा तुमचे स्थान नोंदवण्यासाठी SOS बटण दाबा."
        ),
        "rain": (
            "{location} परिसरात अपेक्षित पर्जन्यमान {rainfall} मिमी, पावसाची शक्यता {rain_chance}% "
            "({observed_at} पर्यंत). धोका पातळी {risk_level} आहे. {action}"
        ),
        "heat": (
            "{location} परिसरात सध्याचे तापमान {temperature}°C आणि आर्द्रता {humidity}% आहे. "
            "धोका पातळी {risk_level} आहे. {action}"
        ),
        "general": (
            "{observed_at} पर्यंत {location} ची ताजी माहिती: {condition}, {temperature}°C, "
            "अपेक्षित पर्जन्यमान {rainfall} मिमी. एकूण धोका {risk_level} ({score}/100). {action}"
        ),
        "unverified": " (टीप: हा अहवाल मॉडेलचा अंदाज आहे, अद्याप अधिकृत स्रोताकडून खात्री देण्यात आलेली नाही.)",
    },
}

# Router-side fallback templates (AI unavailable), per language and role.
# Same format fields the old English-only templates used.
FALLBACK_TEMPLATES = {
    "en": {
        "customer": (
            "The AI assistant is unavailable right now. Based on the current data: "
            "{condition}, about {temperature:.0f}°C with {rainfall:.0f} mm rainfall expected "
            "and {humidity:.0f}% humidity. Overall risk: {risk_level}. "
            "Follow official weather updates and take sensible precautions."
        ),
        "farmer": (
            "The AI assistant is unavailable right now. Field-relevant data: {condition}, "
            "{temperature:.0f}°C, {rainfall:.0f} mm rain expected, wind {wind:.0f} km/h. "
            "Overall risk: {risk_level}. Plan field work around the wettest/windiest hours and "
            "follow local agricultural extension advice for crop-specific decisions."
        ),
        "traveler": (
            "The AI assistant is unavailable right now. Travel-relevant data: {condition}, "
            "{temperature:.0f}°C, {rainfall:.0f} mm rain, wind {wind:.0f} km/h. "
            "Overall risk: {risk_level}. Allow extra journey time and avoid flooded or "
            "exposed routes; monitor conditions before setting out."
        ),
        "disaster_management_officer": (
            "The AI assistant is unavailable right now. Operational data: {condition}, "
            "{temperature:.0f}°C, {rainfall:.0f} mm rain, wind {wind:.0f} km/h; "
            "overall risk {risk_level} (score {risk_score:.0f}/100). "
            "Monitor official IMD/NDMA channels; this is not an official warning."
        ),
    },
    "hi": {
        "customer": (
            "AI सहायक अभी उपलब्ध नहीं है। मौजूदा डेटा के अनुसार: {condition}, तापमान लगभग "
            "{temperature:.0f}°C, अपेक्षित वर्षा {rainfall:.0f} मिमी और नमी {humidity:.0f}%। "
            "समग्र जोखिम: {risk_level}। आधिकारिक मौसम अपडेट देखते रहें और उचित सावधानी बरतें।"
        ),
        "farmer": (
            "AI सहायक अभी उपलब्ध नहीं है। खेती से जुड़ा डेटा: {condition}, {temperature:.0f}°C, "
            "अपेक्षित वर्षा {rainfall:.0f} मिमी, हवा {wind:.0f} किमी/घंटा। समग्र जोखिम: {risk_level}। "
            "सबसे गीले/तेज़ हवा वाले समय के हिसाब से खेत का काम करें और फ़सल-विशिष्ट निर्णयों के "
            "लिए स्थानीय कृषि सलाह अपनाएँ।"
        ),
        "traveler": (
            "AI सहायक अभी उपलब्ध नहीं है। यात्रा से जुड़ा डेटा: {condition}, {temperature:.0f}°C, "
            "वर्षा {rainfall:.0f} मिमी, हवा {wind:.0f} किमी/घंटा। समग्र जोखिम: {risk_level}। "
            "यात्रा में अतिरिक्त समय रखें और बाढ़ वाले या खुले रास्तों से बचें; निकलने से पहले हालात जाँच लें।"
        ),
        "disaster_management_officer": (
            "AI सहायक अभी उपलब्ध नहीं है। परिचालन डेटा: {condition}, {temperature:.0f}°C, "
            "वर्षा {rainfall:.0f} मिमी, हवा {wind:.0f} किमी/घंटा; समग्र जोखिम {risk_level} "
            "(स्कोर {risk_score:.0f}/100)। आधिकारिक IMD/NDMA चैनल देखते रहें; यह आधिकारिक चेतावनी नहीं है।"
        ),
    },
    "mr": {
        "customer": (
            "AI सहाय्यक सध्या उपलब्ध नाही. सध्याच्या डेटानुसार: {condition}, तापमान अंदाजे "
            "{temperature:.0f}°C, अपेक्षित पर्जन्यमान {rainfall:.0f} मिमी आणि आर्द्रता {humidity:.0f}%. "
            "एकूण धोका: {risk_level}. अधिकृत हवामान अपडेट पाहात राहा आणि योग्य खबरदारी घे."
        ),
        "farmer": (
            "AI सहाय्यक सध्या उपलब्ध नाही. शेतीसंबंधी डेटा: {condition}, {temperature:.0f}°C, "
            "अपेक्षित पर्जन्यमान {rainfall:.0f} मिमी, वारा {wind:.0f} किमी/तास. एकूण धोका: {risk_level}. "
            "सर्वात ओल्या/जोरदार वाऱ्याच्या वेळेचा विचार करून शेतकाम नियोजित करा आणि पीक-विशिष्ट "
            "निर्णयांसाठी स्थानिक कृषी सल्ला घे."
        ),
        "traveler": (
            "AI सहाय्यक सध्या उपलब्ध नाही. प्रवासासंबंधी डेटा: {condition}, {temperature:.0f}°C, "
            "पर्जन्यमान {rainfall:.0f} मिमी, वारा {wind:.0f} किमी/तास. एकूण धोका: {risk_level}. "
            "प्रवासासाठी अतिरिक्त वेळ ठेवा आणि पुराचे किंवा उघड्या रस्ते टाळा; निघण्यापूर्वी परिस्थिती तपासा."
        ),
        "disaster_management_officer": (
            "AI सहाय्यक सध्या उपलब्ध नाही. कार्यालयीन डेटा: {condition}, {temperature:.0f}°C, "
            "पर्जन्यमान {rainfall:.0f} मिमी, वारा {wind:.0f} किमी/तास; एकूण धोका {risk_level} "
            "({risk_score:.0f}/100). अधिकृत IMD/NDMA माध्यमांवर लक्ष ठेवा; ही अधिकृत सूचना नाही."
        ),
    },
}

# Appended when the AI answered in the wrong language and the reply was
# replaced with localized data-based guidance (chat router tripwire).
LANGUAGE_MISMATCH_NOTICES = {
    "en": "[The AI could not answer in your selected language — showing localized data guidance instead.]",
    "hi": "[AI आपकी चुनी हुई भाषा में उत्तर नहीं दे पाया — इसके बजाय डेटा आधारित मार्गदर्शन दिखा रहे हैं।]",
    "mr": "[AI तुमच्या निवडलेल्या भाषेत उत्तर देऊ शकला नाही — त्याऐवजी डेटा-आधारित मार्गदर्शन दाखवत आहोत.]",
}

# Appended to fallback replies when the message looks like an emergency.
FALLBACK_EMERGENCY_SUFFIX = {
    "en": " If you are in immediate danger, contact local emergency services (India: 112) or use the SOS panel to log your location.",
    "hi": " अगर आप तुरंत खतरे में हैं, तो स्थानीय आपातकालीन सेवाओं (भारत: 112) से संपर्क करें या अपनी लोकेशन दर्ज करने के लिए SOS पैनल का उपयोग करें।",
    "mr": " तुम्ही तात्काळ धोक्यात असाल तर स्थानिक आपत्कालीन सेवांशी (भारत: 112) संपर्क साधा किंवा तुमचे स्थान नोंदवण्यासाठी SOS पॅनल वापरा.",
}

# Emergency detection in any supported language (Devanagari has no case).
EMERGENCY_KEYWORDS = (
    "emergency", "evacuate", "evacuation", "help", "sos",
    "मदद", "बचाओ", "बचाव", "आपातकाल", "निकासी", "खतरे",
    "मदत", "वाचवा", "आपत्कालीन", "धोक्यात",
)


# Controlled reply for out-of-scope input (scope_guard.py): the user
# asked something that is not weather/safety related.
SCOPE_REFUSAL_MESSAGES = {
    "en": "I can help with weather, forecasts, weather risks, travel conditions, farming guidance, and safety. Please ask a weather-related question.",
    "hi": "मैं मौसम, पूर्वानुमान, मौसम जोखिम, यात्रा की स्थिति, कृषि मार्गदर्शन और सुरक्षा में मदद कर सकता हूँ। कृपया मौसम से जुड़ा सवाल पूछें।",
    "mr": "मी हवामान, अंदाज, हवामान धोके, प्रवास परिस्थिती, शेती मार्गदर्शन आणि सुरक्षिततेत मदत करू शकतो. कृपया हवामानाशी संबंधित प्रश्न विचारा.",
}

# Alias kept for the scope guard's import; same table.
ScopeRefusalMessages = SCOPE_REFUSAL_MESSAGES


def normalize_language(language: str | None) -> str:
    """Clamp any client-supplied language code to a supported one.

    Accepts bare codes ("hi"), BCP-47-ish tags ("hi-IN") and junk;
    unsupported values degrade to English, never to an error.
    """
    base = (language or "").strip().lower().split("-")[0]
    return base if base in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def language_prompt_clause(language: str) -> str:
    """Instruction for LLM providers: exactly which language to answer in."""
    name, native = LANGUAGE_NAMES[language]
    if language == DEFAULT_LANGUAGE:
        return "Respond in English."
    return (
        f"Respond ONLY in {name} ({native}). Write the ENTIRE answer in {name}, "
        "in its native script. Never reply in English, even if the question is "
        "written in English or any other language. Keep numbers, place names and "
        "unit symbols (°C, mm, km/h) as digits."
    )


def translate_condition(condition: str, language: str) -> str:
    """Translate an English weather-condition string for display."""
    table = CONDITIONS.get(language)
    if not table:
        return condition
    return table.get(condition, condition)


def translate_risk_level(level: str, language: str) -> str:
    """Human-readable risk level: upper-case English, native word otherwise."""
    if language == DEFAULT_LANGUAGE:
        return (level or "low").upper()
    return RISK_LEVELS.get(language, {}).get(level, (level or "low").upper())
