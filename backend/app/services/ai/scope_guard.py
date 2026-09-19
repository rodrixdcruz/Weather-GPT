"""
Lightweight scope guard for MausamBagha AI.

Goal: obvious nonsense ("svgsvgsvg", "asdf", a credit-card number) and
clearly unrelated requests ("write me a poem about cats") must NOT burn
an Ollama cold-start or a paid Solar call. Everything else — including
natural-language weather questions that never say the word "weather" —
must pass through untouched.

Deliberately conservative about REFUSING: ambiguity always resolves to
IN_SCOPE because a wasted local-model call is cheap, but rejecting a real
safety question is not.

Escalation is now FREE (see presets.py), so the cost argument that used to
keep knowledge questions on the small local model is gone. Questions that
ask about the phenomenon rather than reporting local conditions are routed
to the free cloud tier, which actually knows the answer — see
`_needs_broad_knowledge`.
"""
import re
from dataclasses import dataclass, field
from enum import Enum

from app.services.ai.translations import ScopeRefusalMessages, normalize_language


class ScopeVerdict(Enum):
    IN_SCOPE = "in_scope"                  # normal MausamBagha AI question → Ollama first
    BROAD_KNOWLEDGE = "broad_knowledge"    # in scope but needs the escalation tier
    OUT_OF_SCOPE = "out_of_scope"          # refuse without any AI call


# Topical terms that can make a message weather/safety-relevant. Single
# words on purpose: "raining", "evacuate", "aqi" all count. Devanagari
# terms cover Hindi/Marathi questions.
_WEATHER_SCOPE_TERMS = frozenset(
    """
    weather rain rainy rainfall drizzle shower showers storm thunderstorm
    thunder lightning flood flooding inundation cyclone hurricane typhoon
    wind windy gust breeze humidity humid temperature temp hot heat heatwave
    heatwave cold coldwave chill fog foggy mist haze smog aqi air pollution
    particulate dust forecast prediction outlook climate monsoon season
    seasonal precipitation snow hail drought
    safe safety unsafe risk risks risky danger dangerous hazard hazardous
    alert warning advisory emergency evacuate evacuation shelter shelters
    sos disaster preparedness response relief
    travel traveling trip journey commute road roads highway driving
    flight flights airport train railway outdoor outdoors outside inside
    umbrella jacket sunscreen
    farm farmer farming agriculture agricultural crop crops field fields
    harvest irrigation sowing pesticide spray spraying livestock
    fisher fishing boat sea coastal marine
    construction site worker labor labour
    school closing open holiday
    today tomorrow yesterday tonight morning afternoon evening week weekend
    now currently currently now
    मौसम बारिश वर्षा बाढ़ तूफ़ान आंधी गर्मी ठंड धूप कोहरा स्मॉग हवा नमी तापमान
    सुरक्षा खतरा चेतावनी आपदा बचाव आश्रय निकासी यात्रा सफ़र सड़क बाहर
    किसान खेती फ़सल सिंचाई कटाई छिड़काव
    पाऊस पावस पर्जन्यमान पूर पुर वादळ वारा उन्हाळा थंडी धुके आर्द्रता तापमान
    सुरक्षित धोका इशारा आपत्ती निवारा प्रवास रस्ता बाहेर
    शेती पीक सिंचन कापणी फवारणी
    """.split()
)

# Phrases that signal a request for general/world knowledge beyond local
# weather context — these justify escalating an otherwise normal question to
# the free cloud tier. (The guard only escalates when the message is
# otherwise weather-relevant; off-topic + broad still resolves OUT_OF_SCOPE
# first.)
_BROAD_KNOWLEDGE_PATTERNS = (
    r"compare\s+\w+\s+(with|to|and)\s+\w+",
    r"(national|global|worldwide|international)\s+(weather|news|forecast)",
    r"histor(y|ical|ically)\s+(weather|rainfall|temperature|data)",
    r"(explain|tell me about|what is|what are)\s+(el\s+ni|la\s+ni|monsoon|climate change|global warming|jet stream)",
    r"climate\s+change",
    r"long\s*term\s+(trend|forecast|outlook)",
)

_BROAD_RE = re.compile("|".join(_BROAD_KNOWLEDGE_PATTERNS), re.IGNORECASE)

# Large-scale climate/science topics that can NEVER be answered from the
# local observation block the model is given. Asking about any of these is a
# knowledge request by definition, so no other signal is needed.
#
# NOTE: this is why bare phrasing patterns were not enough — "Explain what
# El Nino is and how it changes rainfall" missed every pattern above (the
# words after "explain" are not the topic), so a small local model answered
# "my context doesn't include that" instead of the free cloud tier answering
# the actual question.
_GENERAL_KNOWLEDGE_CONCEPTS = (
    "el nino", "elnino", "el niño", "la nina", "la niña",
    "climate change", "global warming", "greenhouse",
    "jet stream", "ozone", "carbon emission", "carbon footprint",
    "weather front", "rain shadow", "urban heat island",
    "monsoon", "sea level", "deforestation",
)

# Asking to have something EXPLAINED, DEFINED or COMPARED — rather than
# reported for the user's own location — is a knowledge request.
_EXPLANATION_TRIGGERS = (
    "explain", "describe", "define", "definition", "meaning of",
    "tell me about", "what is", "what are", "what does", "how does", "how do",
    "why is", "why does", "why do", "what causes", "what makes", "how come",
    "compare", "comparison", "difference between",
    "history of", "historical", "long term", "long-term", "scientific",
)

# Weather phenomena that are general knowledge ONLY when the user asks about
# the phenomenon itself. Deliberately excludes anything present in the local
# observation block (humidity, temperature, rainfall, wind, AQI…): "What is
# the humidity?" must stay a local question, because the local model has the
# real number and the cloud tier would only be slower.
_PHENOMENA = (
    "cyclone", "hurricane", "typhoon", "tornado", "drought",
    "lightning", "thunder", "dew point", "air pressure",
    "formation of", "sea breeze",
)


def _needs_broad_knowledge(text: str) -> bool:
    """True when only a broader-knowledge model can answer this.

    Ordered cheapest-check-first, and intentionally additive: a question
    about a named general concept escalates outright, while a question about
    a weather phenomenon escalates only when it is phrased as a request to
    explain it ("what causes lightning?" yes, "will there be lightning
    today?" no — the local risk engine owns that).
    """
    lowered = text.lower()
    if _BROAD_RE.search(lowered):
        return True
    if any(concept in lowered for concept in _GENERAL_KNOWLEDGE_CONCEPTS):
        return True
    asks_to_explain = any(trigger in lowered for trigger in _EXPLANATION_TRIGGERS)
    if asks_to_explain and any(phenomenon in lowered for phenomenon in _PHENOMENA):
        return True
    return False

# Obvious keyboard-mash / single-token junk.
_WORD_RE = re.compile(r"[A-Za-z\u0900-\u097F]")
_VOWEL_RE = re.compile(r"[aeiouAEIOU]")
_DIGIT_PUNCT_RE = re.compile(r"[\d\s\W]")

_MIN_LENGTH = 3
_MAX_MEANINGFUL_WORDS = 80  # longer inputs are fine; cap protects nothing, just sanity

# Conversational openers that always pass (checked before the gibberish
# heuristics, which would otherwise reject "hi" for being too short).
_GREETINGS = frozenset({"hi", "hello", "hey", "namaste", "नमस्ते", "नमस्कार"})


def _is_gibberish(text: str) -> bool:
    """Heuristics for keyboard-mash input. Never applied to Devanagari."""
    stripped = text.strip()
    if len(stripped) < _MIN_LENGTH:
        return True
    # A single word with no vowels ("svg", "hmm", "wth") is junk; short
    # real words like "hi", "ok", "rain" are handled by length/vowels too
    # ("rain" has a vowel and >= 3 chars → passes).
    words = stripped.split()
    if len(words) == 1:
        word = words[0]
        if not _DIGIT_PUNCT_RE.sub("", word):  # pure digits/punctuation
            return True
        if len(word) >= _MIN_LENGTH and not _VOWEL_RE.search(word) and not any(ord(c) > 127 for c in word):
            return True
    # Extremely low letter ratio → "123 !!!", "....", symbols.
    letters = sum(1 for c in stripped if _WORD_RE.match(c))
    if letters / max(len(stripped), 1) < 0.3:
        return True
    return False


def _topical_score(text: str) -> int:
    lowered = text.lower()
    return sum(1 for term in _WEATHER_SCOPE_TERMS if term in lowered)


@dataclass
class ScopeGuard:
    """Classifies a user message; injectable refusal messages for i18n."""

    refusal_messages: dict = field(default_factory=lambda: ScopeRefusalMessages)

    def classify(self, message: str) -> ScopeVerdict:
        text = (message or "").strip()
        if not text:
            return ScopeVerdict.OUT_OF_SCOPE

        # Openers first: they are legitimate and short ("hi" would fail
        # the gibberish length check otherwise).
        if text.lower() in _GREETINGS or text in _GREETINGS:
            return ScopeVerdict.IN_SCOPE

        if len(text.split()) > _MAX_MEANINGFUL_WORDS:
            # Very long inputs are still in scope — just process them.
            return ScopeVerdict.IN_SCOPE

        if _is_gibberish(text):
            return ScopeVerdict.OUT_OF_SCOPE

        # Broad-knowledge questions are weather/climate-adjacent by
        # definition, so check them BEFORE the topical whitelist —
        # "Tell me about El Nino" has no weather word yet still belongs
        # in scope (with escalation to the free cloud tier).
        if _needs_broad_knowledge(text):
            return ScopeVerdict.BROAD_KNOWLEDGE

        if _topical_score(text) == 0:
            # No topical signal at all: not weather/safety related.
            return ScopeVerdict.OUT_OF_SCOPE

        return ScopeVerdict.IN_SCOPE

    def refusal_message(self, language: str) -> str:
        lang = normalize_language(language)
        return self.refusal_messages.get(lang, self.refusal_messages["en"])


def build_scope_guard(settings=None) -> ScopeGuard:
    """Factory hook (settings reserved for future configurability)."""
    return ScopeGuard()
