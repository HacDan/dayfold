"""Weather and sunrise/sunset for the front page.

Open-Meteo (open-meteo.com) serves the forecast and the place lookup without a key or an account,
so Dayfold can print the day's weather with no credentials to configure.
"""

from __future__ import annotations

import json
import logging
import math
from urllib.parse import urlencode

from . import net
from .settings import WeatherSettings

log = logging.getLogger("dayfold.weather")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# WMO weather codes as Open-Meteo reports them: (pt, en).
CONDITIONS: dict[int, tuple[str, str]] = {
    0: ("Céu limpo", "Clear"),
    1: ("Quase limpo", "Mostly clear"),
    2: ("Parcialmente nublado", "Partly cloudy"),
    3: ("Nublado", "Overcast"),
    45: ("Neblina", "Fog"),
    48: ("Neblina com geada", "Freezing fog"),
    51: ("Garoa fraca", "Light drizzle"),
    53: ("Garoa", "Drizzle"),
    55: ("Garoa forte", "Heavy drizzle"),
    56: ("Garoa congelante", "Freezing drizzle"),
    57: ("Garoa congelante forte", "Heavy freezing drizzle"),
    61: ("Chuva fraca", "Light rain"),
    63: ("Chuva", "Rain"),
    65: ("Chuva forte", "Heavy rain"),
    66: ("Chuva congelante", "Freezing rain"),
    67: ("Chuva congelante forte", "Heavy freezing rain"),
    71: ("Neve fraca", "Light snow"),
    73: ("Neve", "Snow"),
    75: ("Neve forte", "Heavy snow"),
    77: ("Grãos de neve", "Snow grains"),
    80: ("Pancadas de chuva", "Rain showers"),
    81: ("Pancadas moderadas", "Moderate showers"),
    82: ("Pancadas fortes", "Violent showers"),
    85: ("Pancadas de neve", "Snow showers"),
    86: ("Pancadas de neve fortes", "Heavy snow showers"),
    95: ("Tempestade", "Thunderstorm"),
    96: ("Tempestade com granizo", "Thunderstorm with hail"),
    99: ("Tempestade com granizo forte", "Severe thunderstorm with hail"),
}


# US AQI bands: (ceiling, pt, en). Open-Meteo reports the US scale.
AQI_BANDS: list[tuple[int, str, str]] = [
    (50, "Boa", "Good"),
    (100, "Moderada", "Moderate"),
    (150, "Prejudicial a grupos sensíveis", "Unhealthy for sensitive groups"),
    (200, "Prejudicial", "Unhealthy"),
    (300, "Muito prejudicial", "Very unhealthy"),
    (10**9, "Perigosa", "Hazardous"),
]


def aqi_label(value: int, lang: str = "pt") -> str:
    ceiling, pt, en = next(band for band in AQI_BANDS if value <= band[0])  # the last band catches all
    return pt if lang == "pt" else en


def condition_label(code: int | None, lang: str = "pt") -> str:
    pair = CONDITIONS.get(code if code is not None else -1)
    return "—" if pair is None else pair[0] if lang == "pt" else pair[1]


def today(cfg: WeatherSettings) -> dict | None:
    """Today's forecast for the configured place, or ``None`` when it cannot be had.

    The paper prints without it: a forecast is a nicety, not a reason to lose an edition."""
    if not cfg.enabled or cfg.latitude is None or cfg.longitude is None:
        return None
    params = {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        # The place's own day: sunrise in Burlington must not be read on São Paulo's clock just
        # because that is where the schedule runs.
        "timezone": "auto",
        "forecast_days": 2,  # today and tomorrow
        "temperature_unit": "fahrenheit" if cfg.units == "fahrenheit" else "celsius",
    }
    try:
        data = json.loads(net.fetch(f"{FORECAST_URL}?{urlencode(params)}").content)
        daily = data["daily"]
        tomorrow = len(daily["time"]) > 1
        return {
            "place": cfg.place or data.get("timezone", "").split("/")[-1].replace("_", " "),
            "code": int(daily["weather_code"][0]),
            "t_max": _round(daily["temperature_2m_max"][0]),
            "t_min": _round(daily["temperature_2m_min"][0]),
            "sunrise": _clock(daily["sunrise"][0]),
            "sunset": _clock(daily["sunset"][0]),
            "tomorrow_max": _round(daily["temperature_2m_max"][1]) if tomorrow else None,
            "tomorrow_min": _round(daily["temperature_2m_min"][1]) if tomorrow else None,
            "aqi": _air_quality(cfg),
            # The API states the unit it used: trust that over the request, so the page can never
            # print Fahrenheit numbers with a Celsius label (or the reverse).
            "unit": data.get("daily_units", {}).get("temperature_2m_max")
                    or ("°F" if cfg.units == "fahrenheit" else "°C"),
        }
    except Exception as exc:  # noqa: BLE001  any failure just means no weather block
        log.warning("weather for %s, %s unavailable: %s", cfg.place or "?", cfg.latitude, exc)
        return None


def caption(w: dict, labels: dict, lang: str = "pt") -> list[str]:
    """The front page's lines, in the same words, so the page and the cover cannot drift apart."""
    hi, lo, unit = labels["high"], labels["low"], w.get("unit", "")
    lines = [
        f"{w['place']} · {w['condition']} · {hi} {w['t_max']}{unit} · {lo} {w['t_min']}{unit}",
        f"{labels['sunrise']} {w['sunrise']} · {labels['sunset']} {w['sunset']}",
    ]
    outlook = []
    if w.get("tomorrow_max") is not None:
        outlook.append(f"{labels['tomorrow']} {hi} {w['tomorrow_max']}{unit} · {lo} {w['tomorrow_min']}{unit}")
    if w.get("aqi") is not None:
        outlook.append(f"{labels['air_quality']} {w['aqi']} ({aqi_label(w['aqi'], lang)})")
    if outlook:
        lines.append(" · ".join(outlook))
    return lines


def _air_quality(cfg: WeatherSettings) -> int | None:
    """US AQI for the hour, or ``None``: a missing reading is no reason to drop the forecast."""
    params = {"latitude": cfg.latitude, "longitude": cfg.longitude, "current": "us_aqi",
              "timezone": "auto"}
    try:
        data = json.loads(net.fetch(f"{AIR_URL}?{urlencode(params)}").content)
        return int(data["current"]["us_aqi"])
    except Exception as exc:  # noqa: BLE001  the forecast prints without it
        log.warning("air quality for %s unavailable: %s", cfg.place or "?", exc)
        return None


def lookup_place(name: str, lang: str = "pt") -> dict | None:
    """The first match for a place name, so the dashboard can fill in coordinates."""
    params = {"name": name, "count": 1, "language": lang, "format": "json"}
    try:
        found = (json.loads(net.fetch(f"{GEOCODE_URL}?{urlencode(params)}").content)
                 .get("results") or [None])[0]
    except Exception as exc:  # noqa: BLE001  the field stays for the user to fill in
        log.warning("place lookup for %r failed: %s", name, exc)
        return None
    if not found:
        return None
    where = ", ".join(filter(None, [found.get("name"), found.get("admin1"), found.get("country")]))
    return {"place": where or name, "latitude": found["latitude"], "longitude": found["longitude"]}


def _round(value: float) -> int:
    """Half degrees go up: ``round`` would take 17.5 and 28.5 in opposite directions."""
    return math.floor(value + 0.5)


def _clock(stamp: str) -> str:
    """``2026-11-15T05:13`` → ``05:13``."""
    return stamp.split("T", 1)[-1][:5]
