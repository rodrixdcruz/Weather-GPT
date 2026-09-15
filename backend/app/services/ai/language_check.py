"""
Script-based language checking for chat replies.

The tripwire's job is to catch genuinely wrong-language answers: the user
asked in Hindi/Marathi (Devanagari script) and got English back, or asked
in English and got Devanagari. Hindi and Marathi share the Devanagari
script and most emergency/weather vocabulary, so a Devanagari reply is
accepted for EITHER requested language — reliably telling the two apart
needs word-level analysis that misfires far more often than it matters.
(An earlier version tried to return "which language" and could only ever
say en|hi, which wrongly failed every correct Marathi reply.)
"""

# Devanagari block covers both Hindi and Marathi.
_DEVANAGARI_RANGE = ("\u0900", "\u097F")

# A reply is considered native-script when at least this fraction of its
# letters are Devanagari — mixed Devanagari/Latin text (very common in
# real Hindi/Marathi writing) still counts as native-script.
_NATIVE_SCRIPT_FRACTION = 0.5


def is_native_script_reply(text: str) -> bool:
    """True when the reply is predominantly Devanagari (hi or mr)."""
    if not text:
        return False
    total = sum(1 for ch in text if ch.isalpha())
    if total == 0:
        return False
    devanagari = sum(
        1
        for ch in text
        if _DEVANAGARI_RANGE[0] <= ch <= _DEVANAGARI_RANGE[1]
    )
    return devanagari / total >= _NATIVE_SCRIPT_FRACTION


def reply_matches_language(text: str, language: str) -> bool:
    """True when `text` is an acceptable reply for the requested language.

    - en: must NOT be native-script (an English request deserves Latin text).
    - hi / mr (or any Devanagari-requesting tag like 'mr-IN'): any
      predominantly Devanagari reply passes, because the script is the
      script. Only a Latin (English) reply fails.
    """
    requested = (language or "").strip().lower()
    native = is_native_script_reply(text)
    if requested.startswith("hi") or requested.startswith("mr"):
        return native
    return not native
