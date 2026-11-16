"""
Air Control Sensors — главный файл. Собирает ОБЩИЙ КАПИТАН.
Запуск:  python -m streamlit run app.py

Здесь только соединяем части команд:
  backend/data.py          — данные (бэкенд)
  backend/advice_rules.py  — советы по правилам (бэкенд)
  ai/advice_ai.py          — советы от ИИ (команда ИИ)
  ui.py                    — экран (фронтенд)
"""

from pathlib import Path

import streamlit as st

import ui
from ai.advice_ai import get_ai_advice
from backend.advice_rules import get_rule_advice
from backend.data import (CITIES, DISTRICTS, REGIONS, apply_stations, city_place,
                          get_region_aqi, region_place,
                          district_place, get_air, get_cities_aqi,
                          get_districts_aqi, get_hourly, get_stations,
                          nearest_place, nearest_station, search_places, stations_mean,
                          split_now)

st.set_page_config(page_title="Air Control Sensors", page_icon=str(Path(__file__).parent / "assets" / "logo.png"), layout="wide")


@st.cache_data(ttl=600)  # данные обновляем не чаще раза в 10 минут
def load_air(place):
    return get_air(place)


@st.cache_data(ttl=600)
def load_hourly(place):
    return get_hourly(place)


@st.cache_data(ttl=600)
def load_cities_aqi():
    return get_cities_aqi()


@st.cache_data(ttl=600)
def load_districts_aqi(city):
    return get_districts_aqi(city)


@st.cache_data(ttl=600)
def load_region_aqi(region):
    return get_region_aqi(region)


@st.cache_data(ttl=600)
def load_stations(city, token):
    return get_stations(city, token)


@st.cache_data(ttl=3600)
def find_places(query):
    return search_places(query)


@st.cache_data(ttl=1800)  # советы ИИ запоминаем на 30 минут
def load_ai_advice(air, api_key):
    return get_ai_advice(air, api_key)


def secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:  # файла .streamlit/secrets.toml нет
        return ""


# ---------- Где смотрим воздух ----------
sel = ui.show_place_picker(list(CITIES), DISTRICTS, REGIONS)
place = city_place(sel["city"])
district_city = sel["city"] if sel["mode"] == "list" else None
note = None

region = None  # область, чьи районы показать на карте

if sel["mode"] == "list" and sel["district"]:
    place = district_place(sel["city"], sel["district"])
elif sel["mode"] == "region":
    region = sel["region"]
    place = region_place(region, sel["district"])
elif sel["mode"] == "search":
    if sel["query"].strip():
        found = ui.show_search_results(find_places(sel["query"].strip()))
        if found is not None:
            place = found
    else:
        note = "Введите название города выше. Пока показываю Астану."
elif sel["mode"] == "geo":
    if sel["coords"]:
        place = nearest_place(*sel["coords"])
        # если человек в городе с районами — покажем и районы
        for city in DISTRICTS:
            if city in place["name"]:
                district_city = city
        for r in REGIONS:  # человек в районе области — покажем районы области
            if place["name"].endswith(r):
                region = r
    else:
        note = "Пока местоположение не определено, показываю Астану."

# ---------- Данные ----------
air = dict(load_air(place))
df, _ = load_hourly(place)

# реальные уличные датчики aqicn.org (если есть ключ AQICN_TOKEN)
station_city = (district_city or region
                or next((c for c in CITIES if c in place["name"]), None))
stations = load_stations(station_city, secret("AQICN_TOKEN")) if station_city else []
whole_city = sel["mode"] == "list" and not sel["district"]
if whole_city and stations:  # весь город — среднее по всем живым датчикам
    air["aqi"] = stations_mean(stations)
    air["aqi_note"] = f"📡 Среднее по {len(stations)} живым датчикам города (aqicn.org)"
else:
    near = nearest_station(place["lat"], place["lon"], stations)
    if near is not None:  # район или «моё местоположение» — ближайший живой датчик
        air["aqi"] = near["aqi"]
        when = f", {near['time']}" if near["time"] else ""
        air["aqi_note"] = f"📡 Живой датчик «{near['name']}» · {near['km']} км (aqicn.org){when}"
_, past, future = split_now(df)

# ---------- Советы: сначала ИИ, если не вышло — по правилам ----------
ai_key = secret("AI_API_KEY")
advice = None
if ai_key:
    with st.spinner("ИИ готовит советы…"):
        advice = load_ai_advice(air, ai_key)
from_ai = advice is not None
if not from_ai:
    advice = get_rule_advice(air)

# ---------- Экран ----------
ui.show_header(place["name"], air["source"])
if note:
    st.info(note)
ui.show_aqi(air)
ui.show_weather(air)
ui.show_advice(advice, from_ai)
ui.show_charts(df, past, future)
# синяя точка «вы здесь» — только если человек определил своё местоположение
me = None
if sel["mode"] == "geo" and sel["coords"]:
    me = {"lat": sel["coords"][0], "lon": sel["coords"][1], "aqi": air["aqi"]}

if district_city in DISTRICTS:
    rows = apply_stations(load_districts_aqi(district_city), stations)
    ui.show_districts(district_city, rows, me, stations)
elif region in REGIONS:
    rows = apply_stations(load_region_aqi(region), stations)
    ui.show_districts(region, rows, me, stations)
ui.show_map(load_cities_aqi(), me)
