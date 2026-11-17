"""Добирает районы, которые build_regions.py не нашёл.
Запуск из папки проекта:   python tools/fix_regions.py
Ищет медленно, с повтором при отказе сервиса и с латинскими вариантами названий,
и дописывает найденное в backend/regions.py."""
import importlib.util
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_regions as b  # noqa: E402

# Дополнительные варианты названий центров районов (латиница, старые названия)
EXTRA = {
    "Егиндыкольский": ["Yegindykol", "Egindykol", "Егиндыкол"],
    "Байганинский": ["Karauylkeldy", "Karaulkeldy", "Карауылкелди"],
    "Мугалжарский": ["Kandyagash", "Qandyaghash", "Кандагач", "Эмба"],
    "Исатайский": ["Akkystau", "Akkistau", "Аккыстау"],
    "Жангалинский": ["Zhangala", "Dzhangala", "Джангала"],
    "Жанибекский": ["Zhanibek", "Dzhanybek", "Джаныбек"],
    "Шынгырлауский": ["Shyngyrlau", "Chingirlau", "Чингирлау"],
    "Сырымский": ["Zhympity", "Dzhambeyty", "Джамбейты"],
    "Теректинский": ["Fedorovka", "Fyodorovka", "Федоровка"],
    "Аксуский": ["Zhansugurov", "Zhansugirov", "Жансугирово", "Жансугуров"],
    "Каракиянский": ["Kuryk", "Kuryq", "Курык"],
    "Щербактинский": ["Sharbakty", "Shcherbakty", "Щербакты"],
    "Бухар-Жырауский": ["Botakara", "Ботакара"],
    "Нуринский": ["Kiyevka", "Kievka", "Киевка"],
    "Аулиекольский": ["Auliekol", "Semiozernoye", "Семиозерное"],
    "Денисовский": ["Denisovka", "Денисовка"],
    "Наурзумский": ["Karamendy", "Караменды"],
    "Камыстинский": ["Kamysty", "Камысты"],
    "Карабалыкский": ["Karabalyk", "Карабалык"],
    "Костанайский": ["Zatobolsk", "Затобольск"],
    "Жалагашский": ["Zhalagash", "Dzhalagash", "Джалагаш"],
    "Жанакорганский": ["Zhanakorgan", "Dzhanakurgan", "Яныкурган"],
    "Катон-Карагайский": ["Ulken Naryn", "Bolshenarymskoye", "Большенарымское"],
    "Айыртауский": ["Saumalkol", "Volodarskoye", "Володарское"],
    "Габита Мусрепова": ["Novoishimskoye", "Novoishimskiy", "Новоишимское"],
    "Тайыншинский": ["Tayynsha", "Tayinsha", "Krasnoarmeysk", "Красноармейск"],
    "Уалихановский": ["Kishkenekol", "Кишкенеколь"],
    "Байдибекский": ["Shayan", "Шаян"],
    "Жетысайский": ["Zhetysay", "Dzhetysay", "Джетысай"],
    "Отырарский": ["Shauildir", "Shaulder", "Шаульдер"],
    "Казыгуртский": ["Kazygurt", "Qazyghurt", "Казыгурт"],
    "Сайрамский": ["Aksukent", "Аксукент"],
    "Сауранский": ["Shornak", "Шорнак"],
    "Созакский": ["Sholakkorgan", "Chulakkurgan", "Чулаккурган"],
    "Тюлькубасский": ["Turar Ryskulov", "Vannovka", "Ванновка"],
    "Жамбылский": ["Uzynagash", "Asa", "Узынагаш", "Аса"],
}


def get_json(params, tries=4):
    for k in range(tries):
        try:
            r = requests.get(b.GEO_URL, params=params, timeout=20)
            if r.status_code == 429:  # сервис просит подождать
                time.sleep(5 * (k + 1))
                continue
            return r.json().get("results") or []
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return []


def find(names, capital):
    best = None
    for name in names:
        for lang in ("ru", "en"):
            for x in get_json({"name": name, "count": 20, "language": lang,
                               "countryCode": "KZ", "format": "json"}):
                p = (round(x["latitude"], 3), round(x["longitude"], 3))
                d = b.km(p, capital)
                if d <= b.MAX_KM and (best is None or d < best[1]):
                    best = (p, d, name)
            time.sleep(0.8)
        if best:
            return best
    return best


def main():
    path = os.path.join(ROOT, "backend", "regions.py")
    spec = importlib.util.spec_from_file_location("regions", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    regions = mod.REGIONS
    todo = [(r, d, names, cap) for r, (cap, ds) in b.DATA.items()
            for d, names in ds if d not in regions.get(r, {})]
    print(f"Не хватает районов: {len(todo)}. Ищу медленно…")
    still = []
    for i, (region, district, names, capital) in enumerate(todo, 1):
        extra = EXTRA.get(district, [])
        # у «Жамбылский» два разных района: Узынагаш (Алматинская) и Аса (Жамбылская)
        if district == "Жамбылский":
            extra = ["Uzynagash", "Узынагаш"] if "Алматинская" in region else ["Asa", "Аса"]
        hit = find(names + [n for n in extra if n not in names], capital)
        if hit:
            regions.setdefault(region, {})[district] = hit[0]
            print(f"[{i}/{len(todo)}] OK   {region} / {district}: {hit[2]} {hit[0]} ({hit[1]:.0f} км)")
        else:
            still.append(f"{region} / {district}")
            print(f"[{i}/{len(todo)}] НЕТ  {region} / {district}")
    with open(path, "w", encoding="utf-8") as f:
        f.write('"""Районы областей Казахстана: {область: {район: (широта, долгота центра района)}}.\n'
                'Файл создан скриптами tools/build_regions.py и tools/fix_regions.py."""\n\nREGIONS = {\n')
        for region, ds in regions.items():
            f.write(f"    {region!r}: {{\n")
            for d, (la, lo) in ds.items():
                f.write(f"        {d!r}: ({la}, {lo}),\n")
            f.write("    },\n")
        f.write("}\n")
    total = sum(len(v) for v in regions.values())
    print(f"\nГотово: в backend/regions.py теперь {total} районов.")
    if still:
        print("Всё ещё не найдены:\n  " + "\n  ".join(still))


if __name__ == "__main__":
    main()
