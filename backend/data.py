"""
Данные о воздухе и погоде — команда БЭКЕНДА (Азизбек).

Источник: бесплатный сервис Open-Meteo, ключ API не нужен.
  • воздух:  https://air-quality-api.open-meteo.com  (модель CAMS)
  • погода:  https://api.open-meteo.com
  • поиск городов: https://geocoding-api.open-meteo.com
Если интернета нет или сервис не ответил — отдаём демо-данные,
приложение не падает.

МЕСТО (place) — это словарь: {"name": "Алматы", "lat": 43.238, "lon": 76.946}

ДОГОВОРЁННОСТЬ (не менять названия и формат без общего капитана):

  CITIES                    — 20 городов Казахстана: {название: (широта, долгота)}
  DISTRICTS                 — районы городов: {город: {район: (широта, долгота)}}
  city_place(name)          -> place для города из CITIES
  district_place(city, d)   -> place для района
  search_places(text)       -> список place (поиск любого города мира)
  nearest_place(lat, lon)   -> place по координатам пользователя

  get_hourly(place) -> (таблица, источник)
      таблица: колонки time (местное время), utc, pm2_5, pm10, no2, aqi
               (7 дней назад + прогноз вперёд)
      источник: "api" или "demo"

  get_air(place) -> словарь air (то, что сейчас):
      {"city": "Алматы", "aqi": 78, "time": "16:00",
       "pm25": 25.1, "pm10": 41.0, "no2": 12.3,
       "t": -6.0, "h": 72, "p": 1021, "w": 1.8,   # погода (или None)
       "source": "api"}

  get_cities_aqi() -> список {"city", "lat", "lon", "aqi"} для всех CITIES
                      (одним запросом — для карты и рейтинга)
  get_districts_aqi(city) -> то же для районов города

  get_stations(city, token) -> реальные датчики aqicn вокруг города:
                      список {"name", "lat", "lon", "aqi", "time"} (без ключа — [])
  nearest_station(lat, lon, stations, max_km=3) -> ближайший датчик или None
  apply_stations(rows, stations) -> районы с цифрой с датчика, если он ближе 3 км,
                      + поле "source": «📡 датчик …» или «🌐 модель»
"""

import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

# Города республиканского значения и областные центры Казахстана
CITIES = {
    "Астана": (51.169, 71.449),
    "Алматы": (43.238, 76.946),
    "Шымкент": (42.341, 69.590),
    "Актобе": (50.283, 57.167),
    "Караганда": (49.806, 73.085),
    "Тараз": (42.900, 71.367),
    "Павлодар": (52.287, 76.967),
    "Усть-Каменогорск": (49.948, 82.628),
    "Семей": (50.411, 80.227),
    "Атырау": (47.106, 51.920),
    "Костанай": (53.214, 63.632),
    "Кызылорда": (44.853, 65.509),
    "Уральск": (51.233, 51.367),
    "Петропавловск": (54.873, 69.143),
    "Актау": (43.650, 51.160),
    "Туркестан": (43.297, 68.252),
    "Кокшетау": (53.284, 69.377),
    "Талдыкорган": (45.017, 78.373),
    "Конаев": (43.867, 77.067),
    "Жезказган": (47.783, 67.714),
}

# Районы городов (примерные центры). Чтобы добавить город — добавьте его сюда.
DISTRICTS = {
    "Шымкент": {
        "Абайский": (42.360, 69.550),
        "Аль-Фарабийский": (42.320, 69.600),
        "Енбекшинский": (42.300, 69.630),
        "Каратауский": (42.370, 69.650),
        "Туранский": (42.280, 69.550),
    },
}

WAQI_BOUNDS_URL = "https://api.waqi.info/v2/map/bounds"  # реальные датчики (aqicn.org)
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def city_place(name):
    lat, lon = CITIES[name]
    return {"name": name, "lat": lat, "lon": lon}


def district_place(city, district):
    lat, lon = DISTRICTS[city][district]
    return {"name": f"{city}, {district} район", "lat": lat, "lon": lon}


def _distance_km(lat1, lon1, lat2, lon2):
    """Расстояние между двумя точками на Земле, км."""
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_place(lat, lon):
    """Место по координатам пользователя: называем ближайший район или город."""
    best_name, best_km = None, None
    for city, districts in DISTRICTS.items():
        for d, (dlat, dlon) in districts.items():
            km = _distance_km(lat, lon, dlat, dlon)
            if km <= 8 and (best_km is None or km < best_km):
                best_name, best_km = f"{city}, {d} район", km
    if best_name is None:
        for city, (clat, clon) in CITIES.items():
            km = _distance_km(lat, lon, clat, clon)
            if km <= 40 and (best_km is None or km < best_km):
                best_name, best_km = city, km
    name = f"📍 {best_name}" if best_name else "📍 Моё местоположение"
    return {"name": name, "lat": round(lat, 4), "lon": round(lon, 4)}


# ---------------------------------------------------------------------
#  Поиск городов
# ---------------------------------------------------------------------

def search_places(text, count=5):
    """Ищет город по названию. Возвращает список place (может быть пустым)."""
    text = (text or "").strip()
    if len(text) < 2:
        return []
    try:
        r = requests.get(GEO_URL, params={"name": text, "count": count,
                                          "language": "ru", "format": "json"},
                         timeout=10)
        r.raise_for_status()
        results = r.json().get("results") or []
    except Exception:  # noqa: BLE001
        return []
    places = []
    for res in results:
        parts = []
        for p in (res.get("name"), res.get("admin1"), res.get("country")):
            if p and p not in parts:  # без повторов: «Ташкент, Ташкент»
                parts.append(p)
        label = ", ".join(parts)
        places.append({"name": label, "lat": res["latitude"], "lon": res["longitude"]})
    return places


# ---------------------------------------------------------------------
#  Воздух по часам
# ---------------------------------------------------------------------

def _fetch_hourly(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,pm10,nitrogen_dioxide,us_aqi",
        "past_days": 7,  # неделя истории
        "forecast_days": 2,
        "timezone": "auto",  # время города, где бы он ни был
    }
    r = requests.get(AIR_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    h = data["hourly"]
    offset = timedelta(seconds=data.get("utc_offset_seconds", 0))
    time = pd.to_datetime(h["time"])
    df = pd.DataFrame({
        "time": time,
        "utc": time - offset,
        "pm2_5": h["pm2_5"],
        "pm10": h["pm10"],
        "no2": h["nitrogen_dioxide"],
        "aqi": h["us_aqi"],
    })
    return df.dropna(subset=["aqi"])


def _demo_hourly(name):
    """Правдоподобные выдуманные данные, если сервис недоступен."""
    rnd = random.Random(name)  # у каждого города свои, но стабильные цифры
    base = rnd.uniform(30, 110)
    offset = timedelta(hours=5)  # демо-время — казахстанское
    now_utc = _utc_now().replace(minute=0, second=0, microsecond=0)
    rows = []
    for i in range(-24 * 7, 25):  # неделя назад + сутки вперёд
        utc = now_utc + timedelta(hours=i)
        t = utc + offset
        peak = 25 if t.hour in (8, 9, 19, 20, 21) else 0  # пробки и отопление
        aqi = max(10, base + peak + rnd.uniform(-10, 10))
        rows.append({
            "time": t,
            "utc": utc,
            "pm2_5": round(aqi * 0.35, 1),
            "pm10": round(aqi * 0.6, 1),
            "no2": round(aqi * 0.3, 1),
            "aqi": round(aqi),
        })
    return pd.DataFrame(rows)


def get_hourly(place):
    try:
        df = _fetch_hourly(place["lat"], place["lon"])
        if not df.empty:
            return df, "api"
    except Exception:  # noqa: BLE001 — нет интернета, сервис не ответил и т. п.
        pass
    return _demo_hourly(place["name"]), "demo"


def split_now(df):
    """Делит таблицу на «до сейчас» и «прогноз», возвращает текущую строку."""
    now = _utc_now()
    past = df[df["utc"] <= now]
    future = df[df["utc"] > now]
    current = past.iloc[-1] if not past.empty else df.iloc[0]
    return current, past, future


# ---------------------------------------------------------------------
#  Погода сейчас
# ---------------------------------------------------------------------

def _fetch_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        # pressure_msl — давление, приведённое к уровню моря, как на погодных сайтах
        "current": "temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m",
        "wind_speed_unit": "ms",
        "timezone": "auto",
    }
    r = requests.get(WEATHER_URL, params=params, timeout=10)
    r.raise_for_status()
    c = r.json()["current"]
    return {
        "t": c.get("temperature_2m"),
        "h": c.get("relative_humidity_2m"),
        "p": c.get("pressure_msl"),
        "w": c.get("wind_speed_10m"),
    }


def _demo_weather(name):
    rnd = random.Random(name + "weather")
    return {
        "t": round(rnd.uniform(-12, 8), 1),
        "h": round(rnd.uniform(40, 85)),
        "p": round(rnd.uniform(1005, 1030)),
        "w": round(rnd.uniform(0.5, 6), 1),
    }


def get_weather(place):
    """Возвращает (погода, источник)."""
    try:
        return _fetch_weather(place["lat"], place["lon"]), "api"
    except Exception:  # noqa: BLE001
        return _demo_weather(place["name"]), "demo"


# ---------------------------------------------------------------------
#  Всё, что сейчас, одним словарём
# ---------------------------------------------------------------------

def _num(value, digits=1):
    try:
        return None if pd.isna(value) else round(float(value), digits)
    except (TypeError, ValueError):
        return None


def get_air(place):
    df, air_source = get_hourly(place)
    current, _, _ = split_now(df)
    weather, weather_source = get_weather(place)
    source = "api" if air_source == "api" and weather_source == "api" else "demo"
    p = _num(weather.get("p"), 0)
    h = _num(weather.get("h"), 0)
    return {
        "city": place["name"],
        "aqi": int(round(float(current["aqi"]))),
        "time": pd.Timestamp(current["time"]).strftime("%H:%M"),
        "pm25": _num(current["pm2_5"]),
        "pm10": _num(current["pm10"]),
        "no2": _num(current["no2"]),
        "t": _num(weather.get("t")),
        "h": int(h) if h is not None else None,
        "p": int(p) if p is not None else None,
        "w": _num(weather.get("w")),
        "source": source,
    }


# ---------------------------------------------------------------------
#  Все города сразу — для карты и рейтинга
# ---------------------------------------------------------------------

def get_cities_aqi():
    """AQI сейчас во всех CITIES. Один запрос на все города."""
    return _points_aqi(CITIES)


def get_districts_aqi(city):
    """AQI сейчас во всех районах города. Один запрос."""
    return _points_aqi(DISTRICTS.get(city, {}), seed=city)


# ---------------------------------------------------------------------
#  Реальные датчики (aqicn.org, бесплатный ключ AQICN_TOKEN)
# ---------------------------------------------------------------------

def get_stations(city, token, margin=0.15):
    """Реальные уличные датчики вокруг города.
    Возвращает список {"name", "lat", "lon", "aqi", "time"}.
    Нет ключа, нет интернета или датчиков — пустой список."""
    if not token:
        return []
    pts = list(DISTRICTS.get(city, {}).values()) or [CITIES.get(city)]
    pts = [p for p in pts if p]
    if not pts:
        return []
    lat1 = min(p[0] for p in pts) - margin
    lat2 = max(p[0] for p in pts) + margin
    lon1 = min(p[1] for p in pts) - margin
    lon2 = max(p[1] for p in pts) + margin
    try:
        r = requests.get(WAQI_BOUNDS_URL, params={
            "latlng": f"{lat1},{lon1},{lat2},{lon2}",
            "networks": "all",
            "token": token,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            return []
        stations = []
        for s in data.get("data", []):
            try:
                aqi = int(float(s.get("aqi")))  # бывает "-", если датчик молчит
            except (TypeError, ValueError):
                continue
            info = s.get("station") or {}
            stations.append({
                "name": info.get("name") or "Датчик",
                "lat": float(s["lat"]),
                "lon": float(s["lon"]),
                "aqi": aqi,
                "time": str(info.get("time") or "")[11:16],  # «17:00»
            })
        return stations
    except Exception:  # noqa: BLE001
        return []


def nearest_station(lat, lon, stations, max_km=3.0):
    """Ближайший датчик не дальше max_km, или None."""
    best, best_km = None, None
    for s in stations:
        km = _distance_km(lat, lon, s["lat"], s["lon"])
        if km <= max_km and (best_km is None or km < best_km):
            best, best_km = s, km
    return best


def apply_stations(rows, stations, max_km=3.0):
    """Районы, рядом с которыми есть датчик, берут цифру с него.
    Добавляет каждой строке "source": «📡 датчик …» или «🌐 модель»."""
    out = []
    for r in rows:
        s = nearest_station(r["lat"], r["lon"], stations, max_km)
        if s is not None:
            out.append(dict(r, aqi=s["aqi"], source=f"📡 датчик: {s['name']}"))
        else:
            out.append(dict(r, source="🌐 модель"))
    return out


def _points_aqi(points, seed=""):
    """points: {название: (широта, долгота)} -> список {city, lat, lon, aqi}."""
    names = list(points)
    if not names:
        return []
    lats = ",".join(str(points[n][0]) for n in names)
    lons = ",".join(str(points[n][1]) for n in names)
    try:
        r = requests.get(AIR_URL, params={"latitude": lats, "longitude": lons,
                                          "current": "us_aqi"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):  # если город один, сервис отдаёт не список
            data = [data]
        values = [item["current"]["us_aqi"] for item in data]
        if len(values) != len(names) or any(v is None for v in values):
            raise ValueError("incomplete response")
    except Exception:  # noqa: BLE001
        values = [round(random.Random(seed + n).uniform(30, 110)) for n in names]
    return [{"city": n, "lat": points[n][0], "lon": points[n][1], "aqi": int(round(v))}
            for n, v in zip(names, values)]
