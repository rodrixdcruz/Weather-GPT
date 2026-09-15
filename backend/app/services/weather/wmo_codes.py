"""
WMO weather-interpretation codes, as published by Open-Meteo
(https://open-meteo.com/en/docs — WMO codes 0-99). Shared by the
Open-Meteo provider to turn numeric codes into human-readable
descriptions. Kept provider-agnostic on purpose: any provider that
reports WMO codes can reuse it.
"""

# code -> (short label, longer description). Label is compact for cards;
# description is fuller for advisory text.
_WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "Clear sky"),
    1: ("Mainly clear", "Mainly clear sky"),
    2: ("Partly cloudy", "Partly cloudy"),
    3: ("Overcast", "Overcast"),
    45: ("Fog", "Foggy"),
    48: ("Freezing fog", "Freezing fog — icy surfaces possible"),
    51: ("Light drizzle", "Light drizzle"),
    53: ("Drizzle", "Drizzle"),
    55: ("Dense drizzle", "Dense drizzle"),
    56: ("Freezing drizzle", "Freezing drizzle — icy surfaces possible"),
    57: ("Dense freezing drizzle", "Dense freezing drizzle — icy surfaces possible"),
    61: ("Light rain", "Light rain"),
    63: ("Rain", "Rain"),
    65: ("Heavy rain", "Heavy rain"),
    66: ("Freezing rain", "Freezing rain — icy surfaces possible"),
    67: ("Heavy freezing rain", "Heavy freezing rain — icy surfaces possible"),
    71: ("Light snow", "Light snowfall"),
    73: ("Snow", "Snowfall"),
    75: ("Heavy snow", "Heavy snowfall"),
    77: ("Snow grains", "Snow grains"),
    80: ("Light showers", "Light rain showers"),
    81: ("Showers", "Rain showers"),
    82: ("Violent showers", "Violent rain showers"),
    85: ("Snow showers", "Snow showers"),
    86: ("Heavy snow showers", "Heavy snow showers"),
    95: ("Thunderstorm", "Thunderstorm"),
    96: ("Thunderstorm w/ hail", "Thunderstorm with hail"),
    99: ("Thunderstorm w/ hail", "Thunderstorm with heavy hail"),
}


def describe_wmo_code(code: int | None) -> str:
    """Return a human-readable description for a WMO weather code.

    Unknown codes fall back to a neutral description instead of raising —
    the upstream service can add codes before this app learns about them.
    """
    if code is None:
        return "Unknown conditions"
    label, description = _WMO_CODES.get(code, (f"Unrecognized weather code {code}", f"Unrecognized weather code {code}"))
    return description


def describe_wmo_code_short(code: int | None) -> str:
    """Return the compact label for a WMO weather code (cards, stats)."""
    if code is None:
        return "Unknown"
    return _WMO_CODES.get(code, (f"Code {code}", ""))[0]
