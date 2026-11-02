"""Уровни 2–4 для HTTP-слоя: представление игры, CSV и инструкция агента. Миры — в worlds.py."""
import json

from worlds import CONTROL_LEVELS, WORLDS
CODE_RULE = """**Обязательное требование: считай заказ кодом, а не в уме.** Напиши программу (Python или другой язык),
которая берёт данные из `GET /api/state` или `GET /api/export.csv`, считает заказ по явной формуле
(оценка спроса → покрытие до следующего прихода → минус доступный остаток → кратность и минимум)
и сама отправляет `POST /api/order`. В `note` кратко укажи формулу и ключевые числа.
Перед отправкой проверь программой правила заказа. Арифметику «на глаз» не используй."""


def new_state_json(level):
    return json.dumps(WORLDS[level].new_state())


def _played_days(log):
    days = []
    for rep in log:
        days.extend(rep["days"])
    return days


def view(row):
    W, level = WORLDS[row["level"]], row["level"]
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    day = min(state["day"], W.DAYS)
    return {"token": row["id"], "name": row["name"], "level": level, "title": W.TITLE, "control": level in CONTROL_LEVELS,
            "round": state["round"], "rounds": W.ROUNDS, "week": state["round"],
            "day": state["day"], "weekday": W._weekday(day), "finished": W.finished(state),
            "total": state["total"], "orderable": [] if W.finished(state) else W.orderable(state),
            "stock": W.stock_of(state),
            "batches": {k: [{"qty": q, "last_day": e} for q, e in v] for k, v in state["batches"].items()},
            "in_transit": [_transit(W, p, day) for p in state["pending"]],
            "events": W.public_events(day), "events_info": W.public_events_info(day),
            "suppliers_schedule": W.supplier_schedule(state["day"]),
            "world": W.public_world(), "log": log}


def _transit(W, p, day):
    planned, delayed = W.announced_arrival(p, day)
    return {"sku": p["sku"], "qty": p["qty"], "ordered_day": p["ordered"], "planned_day": planned,
            "delay_announced": delayed}


def order(row, data):
    """Возвращает (код, тело, новые поля строки или None)."""
    W = WORLDS[row["level"]]
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    if W.finished(state):
        return 409, {"error": "Игра окончена"}, None
    clean, errors = W.validate_order(data.get("order", {}), state)
    if errors:
        return 400, {"error": "; ".join(errors)}, None
    state, rep = W.play_round(state, clean)
    rep["note"] = str(data.get("note", ""))[:300]
    log.append(rep)
    return 200, None, {"week": state["round"], "stock": json.dumps(state), "total": state["total"],
                       "log": json.dumps(log, ensure_ascii=False)}


def export_csv(row):
    W = WORLDS[row["level"]]
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    head = ("sku;name;supplier;order_days;lead_days;shelf_days;pack;min_order;buy;sell;"
            "day;weekday;sales;stock_end;arrived;written_off;shelf_empty;note")
    out = [head]
    hist_days = W.HISTORY_DAYS
    played = _played_days(log)
    for s in W.SKUS:
        sup = W.SUPPLIERS[s["supplier"]]
        base = [s["sku"], s["name"], sup["name"], "/".join(sup["order_days"]), str(sup["lead"]),
                str(s["shelf"] or ""), str(s["pack"]), str(s["min_order"]), str(s["buy"]), str(s["sell"])]
        h = W.HISTORY[s["sku"]]
        for d, sold, end in zip(hist_days, h["sales"], h["stock_end"]):
            out.append(";".join(base + [str(d), W._weekday(d), str(sold), str(end), "", "", "1" if end == 0 else "0",
                                        "история до игры"]))
        for d in played:
            ln = d["lines"][s["sku"]]
            out.append(";".join(base + [str(d["day"]), d["weekday"], str(ln["sold"]), str(ln["stock_end"]),
                                        str(ln["arrived"]), str(ln["written_off"]), "1" if ln["empty"] else "0",
                                        "сыграно"]))
        if not W.finished(state):
            transit = sum(p["qty"] for p in state["pending"] if p["sku"] == s["sku"])
            note = ("ход " + str(state["round"]) + ", можно заказать сегодня"
                    if s["sku"] in W.orderable(state) else "сегодня поставщик заказы не принимает")
            out.append(";".join(base + [str(state["day"]), W._weekday(state["day"]), "",
                                        str(W.stock_of(state)[s["sku"]]), str(transit), "", "",
                                        note + (f", в пути {transit}" if transit else "")]))
    for e in W.public_events(min(state["day"], W.DAYS)):
        out.append(";".join(["_event", e.replace(";", ",")] + [""] * (head.count(";") - 1)))
    return ("﻿" + "\n".join(out) + "\n").encode("utf-8")


def agent_md(level):
    W = WORLDS[level]
    control = (f"""
**Это контрольный уровень: одна попытка на имя.** Мир другой, чем на уровне {2}: другие спрос, события,
а на уровне 4 — и ассортимент. Программа должна читать товары, поставщиков и правила из `/api/state`,
а не держать их в коде. Отлаживай программу на уровне 2 (там попыток сколько угодно), сюда приходи с готовой.
""" if level in CONTROL_LEVELS else """
Это тренировочный уровень: попыток сколько угодно — отлаживай здесь свою программу.
Потом проверь её на контрольных уровнях 3 и 4: `/agent.md?level=3`, `/agent.md?level=4`.
""")
    return f"""# {W.TITLE} — инструкция для ИИ-агента

Ты закупщик супермаркета. {W.DAYS} дней (день 1 — понедельник), {len(W.SKUS)} товаров, {len(W.SUPPLIERS)} поставщиков.
{control}
Ход — это день заказа: дни {", ".join(map(str, W.ORDER_DAYS))} (пн и чт), всего {W.ROUNDS} ходов.
В каждый ход заказать можно только товары поставщиков, которые принимают заказы в этот день недели
(`orderable` в `/api/state`). После заказа мир проживает дни до следующего хода.

{CODE_RULE}

## Правила мира

- Заказ приезжает утром дня «день заказа + плечо поставщика» и продаётся в тот же день.
  Поставщики иногда задерживают поставки без предупреждения.
- Продажи идут партиями, старые первыми. Партия скоропорта списывается вечером последнего дня годности
  (срок годности — поле `shelf` товара в `world.skus`, в днях).
- Потери за день: нехватка × (цена продажи − закупка) + списание × закупка
  + остаток на вечер × закупка × {W.HOLDING_RATE_DAY:.5f}.
- Спрос зависит от дня недели. Новости (промо, погода, задержки) появляются в `events`, когда о них становится известно.
- Продажи в день с пустой полкой (`shelf_empty=1`) ниже настоящего спроса.
- Правила заказа: целые числа ≥ 0, кратно `pack`, не меньше `min_order` (или 0).
- Каждый поставщик принимает заказы только в свои дни. Если поставщик не работает в день
  первого хода, первый заказ его товаров будет только в следующий его день — рассчитывай на стартовый остаток.

## API (база: https://inventory-lab.tsdpu.org)

Ключ участника выдаёт человек; заголовок `Authorization: Bearer ABCD-EFGH`. Тело запросов — JSON в UTF-8.

- `GET /api/state` — поля:
  - `day`, `weekday`, `round`, `rounds`, `finished`, `total` — где мы и сколько потеряно;
  - `orderable` — товары, которые можно заказать сегодня;
  - `stock` — остаток на утро; `batches[sku]` — партии `{{qty, last_day}}` (`last_day` = null — не портится);
  - `in_transit` — `{{sku, qty, ordered_day, planned_day, delay_announced}}`; объявленная задержка уже учтена в `planned_day`;
  - `suppliers_schedule[поставщик]` — `{{next_order_day, planned_arrival, order_days, lead}}`;
  - `events` — новости текстом; `events_info` — они же структурно: `type` (promo / weather / supplier_delay; бывают и необъявленные изменения спроса),
    `skus`, `day_from`, `day_to`, `uplift_range` [мин, макс], `supplier`, `order_day`, `delay_days`;
  - `world.skus`, `world.suppliers`; `world.history[sku]` — `sales`, `stock_end`, `empty` (1 = полка была пустой)
    по дням `world.history_days` (−27 … 0);
  - `log` — сыгранные ходы: `{{round, from, to, order, cost, cost_parts, days: [{{day, weekday,
    lines: {{sku: {{arrived, sold, stock_end, written_off, empty, cost}}}}}}]}}`.
- `GET /api/export.csv` — всё то же по дням в одной таблице.
- `POST /api/order` — `{{"order": {{"milk": 40, "mince": 12}}, "note": "формула и числа"}}`.
- `GET /api/leaderboard?level={level}`.
"""
