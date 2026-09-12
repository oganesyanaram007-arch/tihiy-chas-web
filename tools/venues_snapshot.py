#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Статический снимок витрины в index.html.

Зачем. Страница была полностью клиентской: в разметке лежал только JSON,
а карточки заведений рисовал JS. На медленной сети гость видел пустой
каталог, пока грузился и выполнялся скрипт, а поисковик — пустую страницу
с обещанием «лучшие места города» и ничем больше.

Теперь карточки лежат в разметке готовыми. JS, загрузившись, перерисует
ленту живыми данными с сервера — статика нужна ровно для первого кадра
и для тех, у кого JS нет.

Запуск:
    python3 tools/venues_snapshot.py                     # взять с прода
    python3 tools/venues_snapshot.py --url http://...    # с другого адреса
    python3 tools/venues_snapshot.py --offline           # пересобрать из
                                                         # уже вшитого JSON
    python3 tools/venues_snapshot.py --check             # ничего не писать

--check возвращает 1, если разметка разошлась с данными: годится для
проверки перед выкаткой.

Снимок обновляется руками или шагом деплоя — он не обязан быть свежим
до минуты. Живые данные всё равно приезжают скриптом; статика отвечает
только за то, чтобы страница не была пустой.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
DEFAULT_URL = "https://tihiy-chas.ru/api/guest/venues"

SEED = re.compile(r'(<script type="application/json" id="venues-seed">\n)(.*?)(\n</script>)', re.S)
GRID = re.compile(r'(<!--venues:start-->)(.*?)(<!--venues:end-->)', re.S)

CAT = {"food": "Ресторан", "coffee": "Кофейня", "beauty": "Красота",
       "spa": "СПА", "fun": "Досуг", "auto": "Авто"}
ICO = {"food": "i-food", "coffee": "i-cup", "beauty": "i-sciss",
       "spa": "i-spa", "fun": "i-key", "auto": "i-drop"}
DIST = {"petro": "Петроградский", "centr": "Центральный", "adm": "Адмиралтейский",
        "vasil": "Василеостровский", "mosk": "Московский", "nev": "Невский",
        "primor": "Приморский", "vyb": "Выборгский", "kalin": "Калининский",
        "kirov": "Кировский", "frunz": "Фрунзенский", "krasnog": "Красногвардейский",
        "krasnos": "Красносельский", "push": "Пушкинский"}
WD = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"]   # v["wd"] по JS: 0 — воскресенье


def esc(v) -> str:
    return html.escape(str(v or ""), quote=True)


def meta(v: dict) -> str:
    """Адрес и район — как это делает venueMeta() на странице."""
    dn, place = DIST.get(v.get("d", ""), ""), (v.get("place") or "").strip()
    if not place:
        return dn
    return f"{place} · {dn}" if dn and dn not in place else place


def rate(v: dict) -> str:
    r = str(v.get("rate") or "").strip()
    if not r:
        return ""
    score = re.fullmatch(r"[0-9]+([.,][0-9]+)?", r)
    return f'<span class="rate">{"★ " + esc(r) if score else esc(r)}</span>'


def weekdays(v: dict) -> str:
    days = v.get("wd") or []
    if len(days) >= 7:
        return "каждый день"
    return ", ".join(WD[d] for d in sorted(days) if 0 <= d < 7)


def card(v: dict) -> str:
    """Та же разметка, что строит feed() в index.html.

    Отличие одно: статика показывает все тихие окна заведения и дни недели,
    а не окна выбранного дня. Снимок не знает, когда его откроют, и врать
    про «сегодня» он не должен.
    """
    slots = sorted(v.get("slots") or [], key=lambda s: s[0])
    if not slots:
        return ""
    best = max(s[1] for s in slots)
    cat = v.get("cat", "food")
    photo = ""
    if v.get("photo"):
        photo = (f'<img class="cover-img" src="{esc(v["photo"])}" alt="" '
                 f'loading="lazy" decoding="async" onerror="this.remove()">')
    chips = "".join(f'<span class="slot">{int(s[0])}:00 · <em>−{int(s[1])}%</em></span>'
                    for s in slots)
    left = esc(v.get("left") or "")
    return (
        '<article class="card shown">'
        '<div class="cover">'
        f'<div class="art art-{esc(cat)}"></div>{photo}<div class="rings"></div>'
        f'<span class="cover-off">−{best}%</span>'
        f'<span class="cover-ic"><svg class="ic" viewBox="0 0 24 24">'
        f'<use href="#{ICO.get(cat, "i-food")}"/></svg></span>'
        f'<span class="cover-cat">{esc(CAT.get(cat, cat))}</span>'
        '</div>'
        '<div class="card-b">'
        f'<div class="card-t"><b>{esc(v.get("name"))}</b>{rate(v)}</div>'
        '<div class="card-m"><svg class="ic" viewBox="0 0 24 24">'
        f'<use href="#i-pin"/></svg>{esc(meta(v))}</div>'
        f'<div class="slots">{chips}</div>'
        '<div class="card-f">'
        f'<span class="left"><i></i>{left or esc(weekdays(v))}</span>'
        '<span class="go">Забронировать <svg class="ic" viewBox="0 0 24 24">'
        '<use href="#i-arrow"/></svg></span>'
        '</div></div></article>')


def render(venues: list[dict]) -> str:
    cards = [c for c in (card(v) for v in venues) if c]
    if not cards:
        # Пустая витрина — тоже осмысленное состояние, но молчать нельзя.
        return ('<div class="empty">Витрина обновляется — загляните через '
                'несколько минут.</div>')
    return "".join(cards)


def fetch(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    venues = data.get("venues") or []
    if not venues:
        raise SystemExit("API вернул пустую витрину — снимок не трогаем")
    return venues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--offline", action="store_true",
                    help="пересобрать разметку из уже вшитого JSON")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    text = INDEX.read_text(encoding="utf-8")
    seed_m, grid_m = SEED.search(text), GRID.search(text)
    if not seed_m:
        print("ОШИБКА: в index.html нет блока venues-seed", file=sys.stderr)
        return 1
    if not grid_m:
        print("ОШИБКА: в index.html нет маркеров <!--venues:start--> / <!--venues:end-->",
              file=sys.stderr)
        return 1

    if args.offline or args.check:
        venues = json.loads(seed_m.group(2))
    else:
        venues = fetch(args.url)

    seed_json = json.dumps(venues, ensure_ascii=False, separators=(",", ":"))
    out = text[:seed_m.start(2)] + seed_json + text[seed_m.end(2):]
    grid_m = GRID.search(out)
    markup = render(venues)
    out = out[:grid_m.start(2)] + markup + out[grid_m.end(2):]

    if args.check:
        if out != text:
            print("Разметка витрины разошлась с venues-seed.", file=sys.stderr)
            print("Запустите: python3 tools/venues_snapshot.py --offline", file=sys.stderr)
            return 1
        print("Витрина в разметке сходится с данными.")
        return 0

    INDEX.write_text(out, encoding="utf-8")
    print(f"Витрина обновлена: {len(venues)} заведений, "
          f"{len(markup)} байт разметки")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
