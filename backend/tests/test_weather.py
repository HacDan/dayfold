"""The front page's weather strip: Open-Meteo forecast and sun times, no key involved."""

import json
from pathlib import Path
from types import SimpleNamespace

from dayfold import weather
from dayfold.edition.i18n import LABELS
from dayfold.settings import WeatherSettings

FORECAST = {
    "latitude": -23.51, "longitude": -46.61, "timezone": "America/Sao_Paulo",
    "daily": {
        "time": ["2026-11-15"],
        "weather_code": [95],
        "temperature_2m_max": [28.7],
        "temperature_2m_min": [17.5],
        "sunrise": ["2026-11-15T05:13"],
        "sunset": ["2026-11-15T18:28"],
    },
}

SAO_PAULO = WeatherSettings(enabled=True, place="São Paulo", latitude=-23.55, longitude=-46.63)


def test_condition_labels():
    assert weather.condition_label(0, "pt") == "Céu limpo"
    assert weather.condition_label(0, "en") == "Clear"
    assert weather.condition_label(95, "en") == "Thunderstorm"
    assert weather.condition_label(None, "en") == "—"
    assert weather.condition_label(1234, "pt") == "—"  # not a WMO code: never guess


def test_today_needs_no_key(monkeypatch):
    seen: dict[str, str] = {}

    def fake_fetch(url: str, **kw):
        seen["url"] = url
        return SimpleNamespace(content=json.dumps(FORECAST).encode())

    monkeypatch.setattr(weather.net, "fetch", fake_fetch)

    assert weather.today(SAO_PAULO) == {
        "place": "São Paulo", "code": 95, "t_max": 29, "t_min": 18,
        "sunrise": "05:13", "sunset": "18:28", "unit": "°C",
    }
    assert seen["url"].startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=-23.55" in seen["url"]
    assert "timezone=auto" in seen["url"]  # the place's own day, not the schedule's clock


def test_caption_puts_the_same_two_lines_on_the_cover():
    """The cover is a front page too: it must not print a pre-weather version of the paper."""
    forecast = {"place": "Burlington, Vermont", "code": 3, "t_max": 43, "t_min": 37,
                "sunrise": "06:49", "sunset": "16:25", "unit": "°F"}
    view = {**forecast, "condition": weather.condition_label(3, "en")}
    view_pt = {**forecast, "condition": weather.condition_label(3, "pt")}

    assert weather.caption(view, LABELS["en"]) == [
        "Burlington, Vermont · Overcast · High 43°F · Low 37°F",
        "Sunrise 06:49 · Sunset 16:25"]
    assert weather.caption(view_pt, LABELS["pt"]) == [
        "Burlington, Vermont · Nublado · Máx. 43°F · Mín. 37°F",
        "Nascer do sol 06:49 · Pôr do sol 16:25"]


def test_today_swaps_between_celsius_and_fahrenheit(monkeypatch):
    """The unit is a setting: it goes out as a request and comes back as the API's own marker."""
    seen: list[str] = []

    def fake_fetch(url: str, **kw):
        seen.append(url)
        unit = "°F" if "temperature_unit=fahrenheit" in url else "°C"
        return SimpleNamespace(content=json.dumps(
            {**FORECAST, "daily_units": {"temperature_2m_max": unit}}).encode())

    monkeypatch.setattr(weather.net, "fetch", fake_fetch)
    fahrenheit = SAO_PAULO.model_copy(update={"units": "fahrenheit"})

    warm = weather.today(fahrenheit)
    cold = weather.today(SAO_PAULO)

    assert "temperature_unit=fahrenheit" in seen[0]
    assert "temperature_unit=celsius" in seen[1]
    assert warm["unit"] == "°F" and cold["unit"] == "°C"
    # The service converts; Dayfold only rounds. A second conversion here would be a bug.
    assert warm["t_max"] == cold["t_max"] == 29
    # If the request and the answer ever disagree, the answer is what the numbers are in.
    monkeypatch.setattr(weather.net, "fetch", lambda url, **kw: SimpleNamespace(
        content=json.dumps({**FORECAST, "daily_units": {"temperature_2m_max": "°C"}}).encode()))
    assert weather.today(fahrenheit)["unit"] == "°C"


def test_half_degrees_round_up(monkeypatch):
    """Half a degree is common in °C; it must not round down on even values only."""
    payload = {**FORECAST, "daily": {**FORECAST["daily"],
                                     "temperature_2m_max": [28.5], "temperature_2m_min": [-3.5]}}
    monkeypatch.setattr(weather.net, "fetch",
                        lambda url, **kw: SimpleNamespace(content=json.dumps(payload).encode()))

    assert weather.today(SAO_PAULO)["t_max"] == 29  # round() would say 28
    assert weather.today(SAO_PAULO)["t_min"] == -3


def test_today_asks_for_nothing_when_it_cannot_deliver(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("no request expected")

    monkeypatch.setattr(weather.net, "fetch", boom)
    assert weather.today(WeatherSettings(enabled=False, latitude=1, longitude=2)) is None
    assert weather.today(WeatherSettings(enabled=True, place="Nowhere")) is None


def test_today_gives_up_quietly_when_the_service_fails(monkeypatch):
    def broken(*a, **kw):
        raise weather.net.FetchError("offline")

    monkeypatch.setattr(weather.net, "fetch", broken)
    assert weather.today(SAO_PAULO) is None


def test_lookup_place(monkeypatch):
    payload = {"results": [{"name": "São Paulo", "admin1": "São Paulo", "country": "Brasil",
                            "latitude": -23.5475, "longitude": -46.63611}]}
    monkeypatch.setattr(weather.net, "fetch",
                        lambda url, **kw: SimpleNamespace(content=json.dumps(payload).encode()))

    assert weather.lookup_place("Sao Paulo", "pt") == {
        "place": "São Paulo, São Paulo, Brasil", "latitude": -23.5475, "longitude": -46.63611,
    }
    monkeypatch.setattr(weather.net, "fetch",
                        lambda url, **kw: SimpleNamespace(content=b'{"generationtime_ms": 0.1}'))
    assert weather.lookup_place("Atlantis", "en") is None


def test_the_front_page_prints_weather_and_sun_times(data_dir, monkeypatch):
    """The forecast is snapshotted with the edition and localised when the paper is typeset."""
    from edition_helpers import add_article, epub_text
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Edition, GenerationJob
    from dayfold.pipeline import generate as gen
    from dayfold.settings import set_section

    monkeypatch.setattr(gen, "collect_all", lambda log: None)
    forecast = {"place": "São Paulo", "code": 3, "t_max": 27, "t_min": 17,
                "sunrise": "05:13", "sunset": "18:29", "unit": "°C"}
    monkeypatch.setattr(gen.weather, "today", lambda cfg: forecast)

    runs = 0

    def build(**weather_cfg) -> str:
        nonlocal runs
        runs += 1
        with session_scope() as s:
            set_section(s, "newspaper", {"include_charge": False, "include_images": False,
                                         "include_games": False, "language": "en"})
            set_section(s, "weather", {"enabled": True, "place": "São Paulo", **weather_cfg})
            add_article(s, "nasa", f"Telescope maps the edge of the solar system, part {runs}")
            job = GenerationJob()
            s.add(job)
            s.flush()
            job_id = job.id
        gen.run_generation_job(job_id)
        with session_scope() as s:
            edition = s.scalar(select(Edition).order_by(Edition.id.desc()).limit(1))
            return epub_text(Path(edition.epub_path))

    text = build(latitude=-23.55, longitude=-46.63)
    assert "São Paulo" in text and "Overcast" in text
    assert "High 27°C" in text and "Low 17°C" in text
    assert "Sunrise 05:13" in text and "Sunset 18:29" in text

    monkeypatch.setattr(gen.weather, "today", lambda cfg: {**forecast, "t_max": 43, "t_min": 37,
                                                          "unit": "°F"})
    assert "High 43°F" in build(latitude=-23.55, longitude=-46.63)  # the unit is a setting

    assert "Sunrise" not in build(enabled=False)  # off is off, not fetched

    monkeypatch.setattr(gen.weather, "today", lambda cfg: None)  # enabled, but the call fails
    assert "Sunrise" not in build(latitude=-23.55, longitude=-46.63)
