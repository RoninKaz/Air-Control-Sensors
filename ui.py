"""
Экран приложения — команда ФРОНТЕНДА (Султан).

Здесь только то, что рисует экран. Данные приходят готовыми
из backend/ и ai/ — сами данные здесь не загружаем.

ДОГОВОРЁННОСТЬ (названия функций не менять):
  show_place_picker(cities, districts) -> словарь выбора:
      {"mode": "list"|"search"|"geo", "city", "district", "query", "coords"}
  show_search_results(results) -> выбранное место или None
  show_header(city, source)
  show_aqi(air)
  show_weather(air)
  show_advice(advice, from_ai)
  show_charts(df, past, future)        — сутки или 7 дней + прогноз
  show_map(rows, me=None)              — города Казахстана (+ синяя точка «вы»)
  show_districts(city, rows, me=None, stations=None)
                                       — районы города (+ «вы» и реальные датчики)
"""

import pandas as pd
import streamlit as st

# Шкала качества воздуха (US AQI): граница, название, цвет плашки, цвет текста
LEVELS = [
    (50, "Хорошо", "#2ecc71", "#0b3d1f"),
    (100, "Умеренно", "#f1c40f", "#3d3000"),
    (150, "Вредно для чувствительных", "#e67e22", "#3d1d00"),
    (200, "Вредно", "#e74c3c", "#ffffff"),
    (300, "Очень вредно", "#8e44ad", "#ffffff"),
    (10_000, "Опасно", "#7f1d1d", "#ffffff"),
]

SHORT = {
    "Хорошо": "воздух чистый",
    "Умеренно": "воздух нормальный для большинства",
    "Вредно для чувствительных": "детям, пожилым и астматикам лучше поберечься",
    "Вредно": "вредно для всех",
    "Очень вредно": "очень вредно, лучше остаться дома",
    "Опасно": "опасно, не выходите без необходимости",
}

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

MODE_LIST = "🏙️ Город из списка"
MODE_SEARCH = "🔎 Поиск города"
MODE_GEO = "📍 Моё местоположение"
WHOLE_CITY = "Весь город"


def level_of(aqi):
    """Возвращает (название, цвет плашки, цвет текста) для AQI."""
    for top, name, color, text in LEVELS:
        if aqi <= top:
            return name, color, text
    return LEVELS[-1][1:]


def _show(value, unit=""):
    return "—" if value is None else f"{value}{unit}"


# ---------------------------------------------------------------------
#  Боковая панель: где смотрим воздух
# ---------------------------------------------------------------------

GEO_ERRORS = {
    0: "Этот браузер не умеет определять местоположение.",
    1: "Доступ к местоположению запрещён. Разрешите его в настройках браузера и телефона "
       "и нажмите «Обновить местоположение».",
    2: "Не удалось определить местоположение. Проверьте, что на телефоне включена геолокация.",
    3: "Определение местоположения заняло слишком долго. Нажмите «Обновить местоположение».",
}


def _ask_location():
    """Определяет местоположение сразу, без маленькой кнопки.
    Возвращает (широта, долгота) или None."""
    try:
        from streamlit_js_eval import get_geolocation
    except ImportError:
        st.warning(
            "Чтобы определять местоположение, установите библиотеку:\n\n"
            "`python -m pip install streamlit-js-eval`"
        )
        return None

    # Большая кнопка: каждое нажатие заново спрашивает браузер
    if "geo_try" not in st.session_state:
        st.session_state.geo_try = 0
    if st.button("🔄 Обновить местоположение", use_container_width=True):
        st.session_state.geo_try += 1

    key = f"geo_{st.session_state.geo_try}"
    try:
        res = get_geolocation(component_key=key)
    except TypeError:  # на случай другой версии библиотеки
        res = get_geolocation()

    if not isinstance(res, dict):
        st.caption("📍 Определяю местоположение… Если браузер спросит — нажмите «Разрешить».")
        return None
    if "error" in res:
        err = res.get("error") or {}
        st.warning(GEO_ERRORS.get(err.get("code"), "Не удалось определить местоположение."))
        return None
    coords = res.get("coords", res)
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def show_place_picker(cities, districts):
    """Выбор места прямо на странице (удобно и на телефоне)."""
    st.markdown("## 🌫️ Air Control Sensors")
    st.caption("Знай, чем дышишь · данные обновляются каждые 10 минут")
    mode = st.radio("Где смотрим воздух?", [MODE_LIST, MODE_SEARCH, MODE_GEO],
                    horizontal=True, label_visibility="collapsed")
    sel = {"mode": "list", "city": cities[0], "district": None, "query": "", "coords": None}

    if mode == MODE_LIST:
        c1, c2 = st.columns(2)
        sel["city"] = c1.selectbox("Город", cities)
        if sel["city"] in districts:
            d = c2.selectbox("Район", [WHOLE_CITY] + list(districts[sel["city"]]))
            if d != WHOLE_CITY:
                sel["district"] = d
    elif mode == MODE_SEARCH:
        sel["mode"] = "search"
        sel["query"] = st.text_input("Название города", placeholder="Например: Ташкент")
    else:
        sel["mode"] = "geo"
        sel["coords"] = _ask_location()
    return sel


def show_search_results(results):
    """Показывает найденные города. Возвращает выбранный или None."""
    if not results:
        st.info("Город не найден. Пока показываю Астану.")
        return None
    labels = [p["name"] for p in results]
    choice = st.selectbox("Найдено", labels)
    return results[labels.index(choice)]


# ---------------------------------------------------------------------
#  Главный экран
# ---------------------------------------------------------------------

def show_header(city, source):
    st.divider()
    st.subheader(f"Качество воздуха: {city}")
    if source == "demo":
        st.warning("Сейчас показаны демо-данные: источник данных недоступен.")


def show_aqi(air):
    name, color, text = level_of(air["aqi"])
    st.markdown(
        f"""
        <div style="background:{color};padding:24px;border-radius:16px;color:{text};">
            <div style="font-size:18px;opacity:.85;">Индекс качества воздуха (AQI) · {air['time']}</div>
            <div style="font-size:64px;font-weight:700;line-height:1.1;">{air['aqi']}</div>
            <div style="font-size:24px;font-weight:600;">{name}</div>
            <div style="font-size:16px;margin-top:8px;">Сейчас {SHORT[name]}.</div>
            {f'<div style="font-size:14px;margin-top:6px;opacity:.85;">{air["aqi_note"]}</div>' if air.get("aqi_note") else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")


def show_weather(air):
    """Компактная сетка: на компьютере 4 в ряд, на телефоне 2 в ряд."""
    st.subheader("Погода и воздух на улице")
    items = [
        ("🌡️ Температура", _show(air.get("t"), " °C")),
        ("💧 Влажность", _show(air.get("h"), " %")),
        ("💨 Ветер", _show(air.get("w"), " м/с")),
        ("🧭 Давление", _show(air.get("p"), " гПа")),
        ("PM2.5", _show(air.get("pm25"), " мкг/м³")),
        ("PM10", _show(air.get("pm10"), " мкг/м³")),
        ("NO₂", _show(air.get("no2"), " мкг/м³")),
    ]
    cells = "".join(
        f'<div style="background:rgba(128,128,128,.12);border-radius:12px;padding:10px 12px;">'
        f'<div style="font-size:13px;opacity:.75;">{label}</div>'
        f'<div style="font-size:22px;font-weight:600;line-height:1.3;">{value}</div></div>'
        for label, value in items
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));'
        f'gap:8px;">{cells}</div>',
        unsafe_allow_html=True,
    )
    st.write("")


def show_advice(advice, from_ai):
    st.subheader("Советы на сегодня")
    cards = [
        ("🧑 Взрослым", advice.get("adults")),
        ("👶 Детям", advice.get("children")),
        ("🫁 Астма и аллергия", advice.get("asthma")),
        ("🏃 Спорт", advice.get("sport")),
    ]
    row1 = st.columns(2)
    row2 = st.columns(2)
    for col, (title, text) in zip(row1 + row2, cards):
        with col.container(border=True):
            st.markdown(f"**{title}**")
            st.write(text or "—")
    with st.container(border=True):
        st.markdown("**🪟 Проветривание**")
        st.write(advice.get("airing") or "—")
    if from_ai:
        st.caption("✨ Советы подготовил ИИ по текущим данным.")
    else:
        st.caption("Советы по шкале AQI.")


def _day(ts):
    ts = pd.Timestamp(ts)
    return f"{WEEKDAYS[ts.weekday()]} {ts:%d.%m}"


def show_charts(df, past, future):
    st.subheader("Как менялся воздух")
    period = st.radio("Период", ["24 часа", "7 дней"], horizontal=True,
                      label_visibility="collapsed")
    left, right = st.columns(2)
    with left:
        if period == "24 часа":
            st.markdown("**Последние 24 часа**")
            st.line_chart(past.tail(24).set_index("time")[["aqi"]], height=260)
        else:
            st.markdown("**Последние 7 дней**")
            week = past.tail(24 * 7).set_index("time")
            st.line_chart(week[["aqi"]], height=260)
            by_day = week["aqi"].resample("D")
            daily = by_day.mean()[by_day.count() >= 12]  # только полные дни
            if len(daily) >= 2:
                st.caption(
                    f"Самый чистый день: {_day(daily.idxmin())} (в среднем AQI {round(daily.min())}). "
                    f"Самый грязный: {_day(daily.idxmax())} (в среднем AQI {round(daily.max())})."
                )
    with right:
        st.markdown("**Прогноз на 24 часа**")
        if future.empty:
            st.info("Прогноза пока нет.")
        else:
            nxt = future.head(24)
            st.line_chart(nxt.set_index("time")[["aqi"]], height=260)
            worst = nxt.loc[nxt["aqi"].idxmax()]
            st.caption(
                f"Хуже всего будет около {pd.Timestamp(worst['time']):%H:%M} — "
                f"AQI {int(worst['aqi'])} ({level_of(worst['aqi'])[0].lower()})."
            )


# ---------------------------------------------------------------------
#  Карты
# ---------------------------------------------------------------------

def _rgb(hex_color):
    return [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]


def _points_table(rows):
    points = []
    for r in rows:
        name, color, _ = level_of(r["aqi"])
        points.append({"lat": r["lat"], "lon": r["lon"], "rgb": _rgb(color),
                       "label": r["city"], "aqi": r["aqi"], "level": name})
    return pd.DataFrame(points).sort_values("aqi")


ME_COLOR = [30, 136, 229]  # синий — «вы здесь»


def _me_table(me):
    name, _, _ = level_of(me["aqi"])
    return pd.DataFrame([{"lat": me["lat"], "lon": me["lon"], "label": "📍 Вы здесь",
                          "aqi": me["aqi"], "level": name}])


def _stations_table(stations):
    rows = []
    for s in stations:
        name, color, _ = level_of(s["aqi"])
        when = f" · {s['time']}" if s.get("time") else ""
        rows.append({"lat": s["lat"], "lon": s["lon"], "rgb": _rgb(color),
                     "label": f"📡 Датчик: {s['name']}{when}",
                     "aqi": s["aqi"], "level": name})
    return pd.DataFrame(rows)


def _draw_map(points, lat, lon, zoom, radius_px, me=None, stations=None):
    """Карта с кружками одного размера на экране и подсказкой при наведении.
    me — {"lat", "lon", "aqi"}: где находится пользователь (синяя точка).
    stations — реальные датчики: маленькие кружки с толстой тёмной обводкой."""
    import pydeck as pdk  # входит в Streamlit

    layers = []
    if stations:
        points = points.assign(rgb=points["rgb"].map(lambda c: c + [150]))  # районы полупрозрачные
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[lon, lat]",
        get_fill_color="rgb",
        get_radius=1,
        radius_min_pixels=radius_px,
        radius_max_pixels=radius_px,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
        pickable=True,
        opacity=0.9,
    )
    layers.append(layer)

    if stations:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=_stations_table(stations),
            get_position="[lon, lat]",
            get_fill_color="rgb",
            get_radius=1,
            radius_min_pixels=9,
            radius_max_pixels=9,
            stroked=True,
            get_line_color=[20, 20, 20],
            line_width_min_pixels=3,
            pickable=True,
        ))

    if me is not None:
        me_df = _me_table(me)
        # мягкий ореол вокруг точки
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=me_df,
            get_position="[lon, lat]",
            get_fill_color=ME_COLOR + [60],
            get_radius=1,
            radius_min_pixels=22,
            radius_max_pixels=22,
            pickable=False,
        ))
        # сама синяя точка с белой обводкой
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=me_df,
            get_position="[lon, lat]",
            get_fill_color=ME_COLOR,
            get_radius=1,
            radius_min_pixels=8,
            radius_max_pixels=8,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=2,
            pickable=True,
        ))

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
        tooltip={"text": "{label}\nAQI {aqi} — {level}"},
    )
    st.pydeck_chart(deck)


def show_map(rows, me=None):
    """rows: список {city, lat, lon, aqi} — города Казахстана.
    me: {"lat", "lon", "aqi"} — где пользователь, или None."""
    st.subheader("Воздух в городах Казахстана")
    points = _points_table(rows)
    best, worst = points.iloc[0], points.iloc[-1]
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("🌿 **Самый чистый воздух**")
        st.markdown(f"### {best['label']}")
        st.caption(f"AQI {best['aqi']} — {best['level'].lower()}")
    with c2.container(border=True):
        st.markdown("🏭 **Самый грязный воздух**")
        st.markdown(f"### {worst['label']}")
        st.caption(f"AQI {worst['aqi']} — {worst['level'].lower()}")

    _draw_map(points, lat=48.0, lon=67.5, zoom=3.6, radius_px=11, me=me)
    hint = "Наведите на кружок, чтобы увидеть город и AQI."
    if me is not None:
        hint += " 🔵 Синяя точка — вы."
    st.caption(hint)
    with st.expander("Рейтинг всех городов"):
        table = points.rename(columns={"label": "Город", "aqi": "AQI", "level": "Уровень"})
        st.dataframe(table[["Город", "AQI", "Уровень"]], hide_index=True)


def show_districts(city, rows, me=None, stations=None):
    """rows: список {city (= район), lat, lon, aqi, source?} — районы города.
    me: {"lat", "lon", "aqi"} — где пользователь, или None.
    stations: реальные датчики (aqicn) или None."""
    if not rows:
        return
    st.subheader(f"Районы: {city}")
    points = _points_table(rows)
    sources = {r["city"]: r.get("source", "🌐 модель") for r in rows}
    points["source"] = points["label"].map(sources)
    _draw_map(points, lat=points["lat"].mean(), lon=points["lon"].mean(),
              zoom=10.6, radius_px=16, me=me, stations=stations)

    legend = ["Наведите на кружок, чтобы увидеть район и AQI."]
    if stations:
        legend.append("Маленькие кружки с тёмной обводкой — 📡 реальные датчики.")
    if me is not None:
        legend.append("🔵 Синяя точка — вы.")
    st.caption(" ".join(legend))

    table = points.rename(columns={"label": "Район", "aqi": "AQI", "level": "Уровень",
                                   "source": "Откуда цифра"})
    st.dataframe(table[["Район", "AQI", "Уровень", "Откуда цифра"]], hide_index=True)

    from_sensor = points["source"].str.startswith("📡").sum()
    if stations:
        st.caption("Датчики: World Air Quality Index Project (aqicn.org) и исходные службы мониторинга.")
    if from_sensor == len(points):
        st.success("📡 Все цифры — с живых уличных датчиков: каждый район берёт данные "
                   "с ближайшего к нему датчика (расстояние указано в таблице).")
    elif from_sensor:
        st.info(f"📡 У {from_sensor} из {len(points)} районов цифра с живого датчика. "
                "Для остальных рядом датчиков нет — показан расчёт модели.")
    elif points["aqi"].max() - points["aqi"].min() <= 3:
        st.info(
            "Сейчас у районов почти одинаковые цифры. Сервис считает воздух по модели "
            "квадратами примерно 45 км, и весь город попадает в один квадрат. "
            "Точную разницу между районами покажут датчики Air Control Sensors, "
            "установленные в каждом районе."
        )

