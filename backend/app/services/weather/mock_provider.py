"""
Mock weather provider. Ported from the frontend demo's `WeatherService`
scenario fixtures so the same five scenarios (normal, heavy_rainfall,
heatwave, thunderstorm, flood_risk) are selectable for demo purposes.
Clearly marked `is_verified=False` and `source="mock_fixture"` — this
must NEVER be presented as verified/live data.
"""
import random
from datetime import datetime, timezone

from app.services.weather.air_quality import AirQuality, us_aqi_band
from app.services.weather.base import ForecastDay, WeatherProvider, WeatherReading, wind_direction_to_compass
from app.services.weather.wmo_codes import describe_wmo_code_short

# Deterministic US-AQI fixture per scenario so air-quality risk is
# demoable offline. Values are mock fixtures and carry is_verified=False
# provenance via the AirQuality model below — never presented as live data.
_SCENARIO_AQI = {
    "normal": 42.0,        # Good band
    "heavy_rainfall": 35.0,  # rain scrubs particulate matter
    "heatwave": 85.0,      # Moderate, typical of stagnant heat
    "thunderstorm": 48.0,
    "flood_risk": 30.0,
    "smog": 168.0,         # Unhealthy — triggers the AIR_QUALITY risk
}

_SCENARIOS = {
    "normal": dict(temperature_c=29, condition="Partly cloudy", rainfall_mm=2, precip_probability_pct=10, humidity_pct=55, wind_kph=12, apparent_temperature_c=31.0, wind_direction_deg=275.0, weather_code=2),
    "heavy_rainfall": dict(temperature_c=25, condition="Heavy rain", rainfall_mm=68, precip_probability_pct=92, humidity_pct=88, wind_kph=22, apparent_temperature_c=26.0, wind_direction_deg=225.0, weather_code=65),
    "heatwave": dict(temperature_c=43, condition="Clear, extreme heat", rainfall_mm=0, precip_probability_pct=2, humidity_pct=28, wind_kph=8, apparent_temperature_c=47.5, wind_direction_deg=90.0, weather_code=0),
    "thunderstorm": dict(temperature_c=27, condition="Thunderstorms", rainfall_mm=34, precip_probability_pct=80, humidity_pct=78, wind_kph=38, apparent_temperature_c=30.0, wind_direction_deg=180.0, weather_code=95),
    "flood_risk": dict(temperature_c=26, condition="Persistent heavy rain", rainfall_mm=110, precip_probability_pct=97, humidity_pct=91, wind_kph=26, apparent_temperature_c=28.0, wind_direction_deg=200.0, weather_code=65),
    "smog": dict(temperature_c=24, condition="Hazy smog", rainfall_mm=0, precip_probability_pct=5, humidity_pct=62, wind_kph=6, apparent_temperature_c=26.0, wind_direction_deg=45.0, weather_code=45),
}


class MockWeatherProvider(WeatherProvider):
    def __init__(self, scenario: str = "normal") -> None:
        self.scenario = scenario if scenario in _SCENARIOS else "normal"

    async def get_current(self, latitude: float, longitude: float) -> WeatherReading:
        base = _SCENARIOS[self.scenario]
        wind_dir = base["wind_direction_deg"]
        us_aqi = _SCENARIO_AQI[self.scenario]
        air_quality = AirQuality(
            observed_at=datetime.now(timezone.utc).isoformat(),
            us_aqi=us_aqi,
            pm2_5=round(us_aqi * 0.45, 1),
            pm10=round(us_aqi * 0.75, 1),
            band=us_aqi_band(us_aqi),
            source="mock_fixture",
            is_verified=False,  # mock fixture — never presented as live AQI
        )
        return WeatherReading(
            location_label=f"{latitude:.3f}, {longitude:.3f}",
            latitude=latitude,
            longitude=longitude,
            observed_at=datetime.now(timezone.utc).isoformat(),
            source="mock_fixture",
            is_verified=False,
            temperature_c=base["temperature_c"],
            condition=base["condition"],
            rainfall_mm=base["rainfall_mm"],
            precip_probability_pct=base["precip_probability_pct"],
            humidity_pct=base["humidity_pct"],
            wind_kph=base["wind_kph"],
            apparent_temperature_c=base["apparent_temperature_c"],
            wind_direction_deg=wind_dir,
            wind_direction=wind_direction_to_compass(wind_dir),
            wind_gust_kph=round(base["wind_kph"] * 1.4, 1),
            weather_code=base["weather_code"],
            air_quality=air_quality,
        )

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7) -> list[ForecastDay]:
        base = _SCENARIOS[self.scenario]
        out = []
        for i in range(days):
            jitter = random.uniform(0.7, 1.3)
            rain = round(base["rainfall_mm"] * jitter, 1)
            temp = round(base["temperature_c"] * random.uniform(0.95, 1.05), 1)
            day_code = base["weather_code"]
            out.append(
                ForecastDay(
                    date=f"day{i + 1}",
                    rainfall_mm=rain,
                    temperature_c=temp,
                    precipitation_probability_pct=min(100.0, base["precip_probability_pct"] * jitter),
                    condition=describe_wmo_code_short(day_code) if base["condition"] != "Clear, extreme heat" else "Clear sky",
                    weather_code=day_code,
                    apparent_temperature_max_c=round(base["apparent_temperature_c"] * jitter, 1),
                    wind_max_kph=round(base["wind_kph"] * 1.2, 1),
                )
            )
        return out
