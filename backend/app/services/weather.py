from dataclasses import dataclass
from datetime import datetime

import httpx

from ..core.config import settings


@dataclass(frozen=True)
class WeatherResult:
    summary: str
    temperature_c: float | None = None
    precipitation_probability: int | None = None


class WeatherProvider:
    name = "none"

    def forecast(self, location: str | None, event_time: str | None) -> WeatherResult | None:
        return None


class OpenWeatherProvider(WeatherProvider):
    name = "openweather"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def forecast(self, location: str | None, event_time: str | None) -> WeatherResult | None:
        if not location:
            return None
        try:
            response = httpx.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"q": location, "appid": self.api_key, "units": "metric", "cnt": 8},
                timeout=5.0,
            )
            response.raise_for_status()
            forecasts = response.json().get("list", [])
            if not forecasts:
                return None
            selected = forecasts[0]
            if event_time:
                try:
                    target_hour = int(event_time.split(":")[0])
                    selected = min(forecasts, key=lambda row: abs(datetime.fromtimestamp(row["dt"]).hour - target_hour))
                except (ValueError, KeyError, TypeError):
                    pass
            description = selected.get("weather", [{}])[0].get("description")
            temperature = selected.get("main", {}).get("temp")
            rain = selected.get("pop", 0)
            if not description:
                return None
            return WeatherResult(
                summary=f"Forecast: {description}, {temperature:g}°C" if isinstance(temperature, (int, float)) else f"Forecast: {description}",
                temperature_c=temperature if isinstance(temperature, (int, float)) else None,
                precipitation_probability=round(rain * 100) if isinstance(rain, (int, float)) else None,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None


def get_weather_provider() -> WeatherProvider:
    if settings.weather_provider == "openweather" and settings.weather_api_key:
        return OpenWeatherProvider(settings.weather_api_key)
    return WeatherProvider()
