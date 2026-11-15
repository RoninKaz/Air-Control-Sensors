"""Проверка ИИ-советов. Запуск из папки проекта:
    python tests/check_ai.py
Показывает, есть ли ключ, и точную ошибку OpenAI (сам ключ не печатает)."""
import json
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

path = os.path.join(".streamlit", "secrets.toml")
try:
    with open(path, "rb") as f:
        secrets = tomllib.load(f)
except Exception as e:
    sys.exit(f"[1] Не удалось прочитать {path}: {e}")

key = str(secrets.get("AI_API_KEY", "")).strip()
if not key:
    sys.exit("[1] В secrets.toml нет строки AI_API_KEY = \"sk-...\"")
print(f"[1] Ключ найден: {key[:5]}...{key[-4:]} (длина {len(key)})")

try:
    import openai
    print(f"[2] Библиотека openai {openai.__version__} установлена")
except Exception as e:
    sys.exit(f"[2] Библиотека openai не загружается: {e}")

from ai.advice_ai import MODEL, get_ai_advice
print(f"[3] Модель: {MODEL}. Пробую простой запрос…")
try:
    client = openai.OpenAI(api_key=key, timeout=20)
    r = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": "Ответь одним словом: привет"}])
    print("[3] OpenAI ответил:", r.choices[0].message.content)
except Exception as e:
    sys.exit(f"[3] ОШИБКА OpenAI: {type(e).__name__}: {e}")

air = {"city": "Шымкент", "aqi": 88, "time": "17:00", "pm25": 26.0, "pm10": 41.0,
       "no2": 12.3, "t": 11.5, "h": 43, "p": 1023, "w": 1.6, "source": "api"}
advice = get_ai_advice(air, key)
if advice is None:
    print("[4] get_ai_advice вернула None — OpenAI работает, но ответ не прошёл проверки в функции.")
else:
    print("[4] Всё работает! Советы:")
    print(json.dumps(advice, ensure_ascii=False, indent=2))
