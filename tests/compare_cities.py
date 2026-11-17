"""Цифры приложения для 5 городов — чтобы сравнить с iqair.com и погодными сайтами.
Запуск из папки проекта:  python tests/compare_cities.py"""
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.data import city_place, get_air, get_stations, stations_mean  # noqa: E402

try:
    with open(os.path.join(".streamlit", "secrets.toml"), "rb") as f:
        token = str(tomllib.load(f).get("AQICN_TOKEN", ""))
except Exception:  # noqa: BLE001
    token = ""

print(f"{'Город':<10} {'время':>5} {'AQI модель':>10} {'AQI датчики':>11} {'PM2.5':>6} "
      f"{'°C':>6} {'влаж%':>5} {'ветер':>5} {'гПа':>5}")
for city in ["Астана", "Алматы", "Шымкент", "Караганда", "Актобе"]:
    a = get_air(city_place(city))
    st = get_stations(city, token) if token else []
    sens = f"{stations_mean(st)} ({len(st)} шт)" if st else "—"
    print(f"{city:<10} {a['time']:>5} {a['aqi']:>10} {sens:>11} {a['pm25']!s:>6} "
          f"{a['t']!s:>6} {a['h']!s:>5} {a['w']!s:>5} {round(a['p']) if a['p'] else '—'!s:>5}"
          + ("   (ДЕМО — нет интернета?)" if a["source"] != "api" else ""))
