#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разносит продуктовые факты из content/product.json по всему проекту.

Зачем это нужно. Одни и те же цифры и условия были написаны в разметке
руками в десятке мест и разошлись между собой: hero обещал депозит,
лента — бесплатную бронь, карточка брони — «тестовый режим», шаг 03
говорил «называете код», а FAQ на той же странице — «показываете QR».
Это не опечатки, а отсутствие источника правды.

Теперь источник один — content/product.json. Здесь он превращается в:

  · подстановку в HTML между маркерами <!--p:ключ-->…<!--/p-->
    (значение попадает в разметку статически, поэтому страница остаётся
    осмысленной с выключенным JS и для поисковиков);
  · content/product.js — те же значения для клиентского кода
    (калькулятор, карточка брони, мини-апп);
  · app/product.py в репозитории бота — те же значения для бэкенда.

Запуск:
    python3 tools/product.py            # разнести значения
    python3 tools/product.py --check    # только проверить, ничего не писать

--check возвращает код 1, если хоть один файл разошёлся с product.json.
Держите его в приёмочных тестах: он ловит ручную правку цифры в разметке.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "content" / "product.json"

# Страницы, в которых работают маркеры <!--p:…-->
PAGES = ["index.html", "app.html", "guest.html", "login.html",
         "tihiy-chas-cabinet.html", "404.html"]

# Бэкенд лежит в отдельном репозитории рядом. Если его нет (например, на
# машине, где клонирован только сайт) — молча пропускаем, сайт самодостаточен.
BOT_APP = ROOT.parent / "tihiy-chas-bot" / "app"

MARKER = re.compile(r"(<!--p:([A-Za-z0-9_.]+)-->)(.*?)(<!--/p-->)", re.S)
SCRIPT = re.compile(r'(<script src="/content/product\.js)(\?v=[0-9a-f]+)?(")')


# ---------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------

def rub(n: int) -> str:
    """1990 → «1 990 ₽». Разделитель — обычный пробел, как уже принято на сайте."""
    return f"{n:,}".replace(",", " ") + " ₽"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 час, 2 часа, 5 часов."""
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return f"{n} {one}"
    if 2 <= mod10 <= 4 and not 10 <= mod100 < 20:
        return f"{n} {few}"
    return f"{n} {many}"


ORDINAL = {1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого",
           5: "пятого", 6: "шестого", 7: "седьмого"}


def load() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def values(p: dict) -> dict:
    """Плоский словарь подстановок для шаблонов в copy."""
    money, plans = p["money"], p["plans"]
    prices = {it["id"]: it for it in plans["items"]}
    return {
        "deposit": rub(money["deposit"]),
        "depositNum": str(money["deposit"]),
        "venueDiscount": rub(money["venueBillDiscount"]),
        "freeFromVisitOrdinal": ORDINAL.get(money["freeFromVisit"], str(money["freeFromVisit"])),
        "discountRange": f'{p["discount"]["min"]}–{p["discount"]["max"]}%',
        "discountMin": str(p["discount"]["min"]),
        "discountMax": str(p["discount"]["max"]),
        "cancelHours": plural(p["booking"]["cancelFreeHours"], "час", "часа", "часов"),
        "horizonDays": plural(p["booking"]["horizonDays"], "день", "дня", "дней"),
        "districts": str(p["geo"]["districts"]),
        "city": p["geo"]["city"],
        "planMin": rub(min(it["price"] for it in plans["items"])),
        "planStandard": rub(prices["standard"]["price"]),
        "planStandardName": prices["standard"]["name"],
        "foodCostPct": str(p["calc"]["foodCostPct"]),
        "bot": p["support"]["telegramBot"],
    }


def copy(p: dict) -> dict:
    """Готовые фразы: подставлены числа и выбран вариант под состояние оплаты.

    Правило выбора варианта: базовый ключ — состояние «оплата не подключена»,
    ключ с суффиксом Charged — «деньги с гостя списываются». В разметке
    ставится всегда базовый ключ, переключение делает этот код.
    """
    v = values(p)
    charged = bool(p["money"]["depositCharged"])
    raw = {k: s for k, s in p["copy"].items() if not k.startswith("_")}
    out = {}
    for key, template in raw.items():
        if key.endswith("Charged"):
            continue
        if charged and (key + "Charged") in raw:
            template = raw[key + "Charged"]
        out[key] = template.format(**v)
    return out


def render_map(p: dict) -> dict:
    """Всё, что может встретиться в маркере <!--p:ключ-->."""
    out = {f"copy.{k}": s for k, s in copy(p).items()}
    for k, s in values(p).items():
        out[k] = s
    out["code.example"] = "".join(p["code"]["alphabet"][i % len(p["code"]["alphabet"])]
                                  for i in (7, 19, 2, 25, 11, 4))
    for it in p["plans"]["items"]:
        out[f'plan.{it["id"]}.name'] = it["name"]
        out[f'plan.{it["id"]}.price'] = rub(it["price"])
        out[f'plan.{it["id"]}.note'] = it.get("note", "")
        # Список возможностей отдаётся готовой разметкой: иконка-галочка
        # одна и та же во всех тарифах, дублировать её в JSON незачем.
        out[f'plan.{it["id"]}.features'] = "".join(
            f'<li><svg class="ic" viewBox="0 0 24 24"><use href="#i-check"/></svg>{f}</li>'
            for f in it.get("features", []))
    return out


# ---------------------------------------------------------------------
# Цели генерации
# ---------------------------------------------------------------------

def js(p: dict) -> str:
    payload = {
        "deposit": p["money"]["deposit"],
        "depositCharged": p["money"]["depositCharged"],
        "venueBillDiscount": p["money"]["venueBillDiscount"],
        "freeFromVisit": p["money"]["freeFromVisit"],
        "discountMin": p["discount"]["min"],
        "discountMax": p["discount"]["max"],
        "horizonDays": p["booking"]["horizonDays"],
        "cancelFreeHours": p["booking"]["cancelFreeHours"],
        "noShowPolicy": p["booking"]["noShowPolicy"],
        "redeemPrimary": p["redeem"]["primary"],
        "points": {k: v for k, v in p["points"].items()
                   if not k.startswith("_")},
        "codeLength": p["code"]["length"],
        "codeAlphabet": p["code"]["alphabet"],
        "districts": p["geo"]["districts"],
        "plans": p["plans"]["items"],
        "calc": {k: v for k, v in p["calc"].items() if not k.startswith("_")},
        "bot": p["support"]["telegramBot"],
        "text": copy(p),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return ("/* Сгенерировано из content/product.json — руками не править.\n"
            "   Правьте product.json и запускайте: python3 tools/product.py */\n"
            f"window.PRODUCT = {body};\n")


def py(p: dict) -> str:
    m, c = p["money"], copy(p)
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Продуктовые константы. Сгенерировано из content/product.json',
        "сайта (репозиторий tihiy-chas-web) — руками не править.",
        "",
        "Правьте product.json и запускайте: python3 tools/product.py",
        '"""',
        "",
        f'DEPOSIT = {m["deposit"]}                    # ₽, комиссия платформы, платит гость',
        f'DEPOSIT_CHARGED = {bool(m["depositCharged"])}          # списываются ли деньги сейчас',
        f'VENUE_BILL_DISCOUNT = {m["venueBillDiscount"]}       # ₽, скидка заведения к счёту',
        f'FREE_FROM_VISIT = {m["freeFromVisit"]}             # с какого визита в то же заведение визит бесплатен',
        f'DISCOUNT_MIN = {p["discount"]["min"]}',
        f'DISCOUNT_MAX = {p["discount"]["max"]}',
        f'HORIZON_DAYS = {p["booking"]["horizonDays"]}',
        f'CANCEL_FREE_HOURS = {p["booking"]["cancelFreeHours"]}',
        f'NO_SHOW_POLICY = {p["booking"]["noShowPolicy"]!r}',
        f'REDEEM_PRIMARY = {p["redeem"]["primary"]!r}       # код — основное, QR — ускоритель',
        f'CODE_LENGTH = {p["code"]["length"]}',
        f'POINTS_PER_BOOKING = {p["points"]["perBooking"]}',
        f'POINTS_PER_VISIT = {p["points"]["perVisit"]}',
        f'POINTS_NEW_VENUE_MULT = {p["points"]["newVenueMultiplier"]}',
        f'POINTS_REFERRAL = {p["points"]["referral"]}',
        f'CODE_ALPHABET = {p["code"]["alphabet"]!r}',
        f'CODE_LEGACY_PREFIX = {p["code"]["legacyPrefix"]!r}',
        f'DISTRICTS = {p["geo"]["districts"]}',
        f'SUPPORT_BOT = {p["support"]["telegramBot"]!r}',
        "",
        "# Формулировки — те же, что на сайте, чтобы бот не говорил своими словами.",
        "TEXT = {",
    ]
    for k in sorted(c):
        lines.append(f"    {k!r}: {c[k]!r},")
    lines += ["}", ""]
    return "\n".join(lines)


def stamp_version(text: str, version: str) -> str:
    """Дописывает метку версии к ссылке на product.js.

    На статику nginx ставит кэш в тридцать дней, а имя файла не меняется.
    Без метки правка цены доехала бы до гостя через месяц — а до тех, кто
    уже открывал сайт, не доехала бы вовсе.
    """
    return SCRIPT.sub(lambda m: f"{m.group(1)}?v={version}{m.group(3)}", text)


def substitute(text: str, rmap: dict, where: str, problems: list) -> str:
    def repl(m):
        open_tag, key, _old, close_tag = m.groups()
        if key not in rmap:
            problems.append(f"{where}: неизвестный ключ <!--p:{key}-->")
            return m.group(0)
        return f"{open_tag}{rmap[key]}{close_tag}"
    return MARKER.sub(repl, text)


def main() -> int:
    check = "--check" in sys.argv
    p = load()
    rmap = render_map(p)
    problems: list[str] = []
    stale: list[str] = []

    targets: list[tuple[pathlib.Path, str]] = []

    js_body = js(p)
    version = hashlib.sha256(js_body.encode("utf-8")).hexdigest()[:8]

    for name in PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        before = path.read_text(encoding="utf-8")
        after = stamp_version(substitute(before, rmap, name, problems), version)
        targets.append((path, after))
        if before != after:
            stale.append(name)

    targets.append((ROOT / "content" / "product.js", js_body))
    if BOT_APP.is_dir():
        targets.append((BOT_APP / "product.py", py(p)))

    for path, content in targets:
        if path.suffix in (".js", ".py"):
            old = path.read_text(encoding="utf-8") if path.exists() else None
            if old != content:
                rel = path.relative_to(ROOT) if ROOT in path.parents else path
                stale.append(str(rel))

    if problems:
        for line in problems:
            print("ОШИБКА:", line, file=sys.stderr)
        return 1

    if check:
        if stale:
            print("Разошлись с content/product.json:", file=sys.stderr)
            for name in stale:
                print("  ·", name, file=sys.stderr)
            print("\nЗапустите: python3 tools/product.py", file=sys.stderr)
            return 1
        print("Всё сходится с content/product.json.")
        return 0

    for path, content in targets:
        path.write_text(content, encoding="utf-8")
    marks = sum(len(MARKER.findall((ROOT / n).read_text(encoding="utf-8")))
                for n in PAGES if (ROOT / n).exists())
    print(f"Обновлено файлов: {len(targets)}, подстановок в разметке: {marks}")
    if not BOT_APP.is_dir():
        print(f"Репозиторий бота не найден ({BOT_APP}) — app/product.py пропущен.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
