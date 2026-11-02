"""Уровень 2 для HTTP-слоя: представление игры, CSV и инструкция агента. Логика мира — в sim2."""
import json

import sim2

TITLE = "Уровень 2 · Супермаркет (дни, 10 товаров)"
CODE_RULE = """**Обязательное требование: считай заказ кодом, а не в уме.** Напиши программу (Python или другой язык),
которая берёт данные из `GET /api/state` или `GET /api/export.csv`, считает заказ по явной формуле
(оценка спроса → покрытие до следующего прихода → минус доступный остаток → кратность и минимум)
и сама отправляет `POST /api/order`. В `note` кратко укажи формулу и ключевые числа.
Перед отправкой проверь программой правила заказа. Арифметику «на глаз» не используй."""


def new_state_json():
    return json.dumps(sim2.new_state())


def _played_days(log):
    days = []
    for rep in log:
        days.extend(rep["days"])
    return days


def view(row):
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    day = min(state["day"], sim2.DAYS)
    return {"token": row["id"], "name": row["name"], "level": 2, "title": TITLE,
            "round": state["round"], "rounds": sim2.ROUNDS, "week": state["round"],
            "day": state["day"], "weekday": sim2._weekday(day), "finished": sim2.finished(state),
            "total": state["total"], "orderable": [] if sim2.finished(state) else sim2.orderable(state),
            "stock": sim2.stock_of(state),
            "batches": {k: [{"qty": q, "last_day": e} for q, e in v] for k, v in state["batches"].items()},
            "in_transit": [{"sku": p["sku"], "qty": p["qty"], "ordered_day": p["ordered"],
                            "planned_day": p["planned"]} for p in state["pending"]],
            "events": sim2.public_events(day), "world": sim2.public_world(), "log": log}


def order(row, data):
    """Возвращает (код, тело, новые поля строки или None)."""
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    if sim2.finished(state):
        return 409, {"error": "Игра окончена"}, None
    clean, errors = sim2.validate_order(data.get("order", {}), state)
    if errors:
        return 400, {"error": "; ".join(errors)}, None
    state, rep = sim2.play_round(state, clean)
    rep["note"] = str(data.get("note", ""))[:300]
    log.append(rep)
    return 200, None, {"week": state["round"], "stock": json.dumps(state), "total": state["total"],
                       "log": json.dumps(log, ensure_ascii=False)}


def export_csv(row):
    state, log = json.loads(row["stock"]), json.loads(row["log"])
    head = ("sku;name;supplier;order_days;lead_days;shelf_days;pack;min_order;buy;sell;"
            "day;weekday;sales;stock_end;arrived;written_off;shelf_empty;note")
    out = [head]
    hist_days = sim2.HISTORY_DAYS
    played = _played_days(log)
    for s in sim2.SKUS:
        sup = sim2.SUPPLIERS[s["supplier"]]
        base = [s["sku"], s["name"], sup["name"], "/".join(sup["order_days"]), str(sup["lead"]),
                str(s["shelf"] or ""), str(s["pack"]), str(s["min_order"]), str(s["buy"]), str(s["sell"])]
        h = sim2.HISTORY[s["sku"]]
        for d, sold, end in zip(hist_days, h["sales"], h["stock_end"]):
            out.append(";".join(base + [str(d), sim2._weekday(d), str(sold), str(end), "", "", "1" if end == 0 else "0",
                                        "история до игры"]))
        for d in played:
            ln = d["lines"][s["sku"]]
            out.append(";".join(base + [str(d["day"]), d["weekday"], str(ln["sold"]), str(ln["stock_end"]),
                                        str(ln["arrived"]), str(ln["written_off"]), "1" if ln["empty"] else "0",
                                        "сыграно"]))
        if not sim2.finished(state):
            transit = sum(p["qty"] for p in state["pending"] if p["sku"] == s["sku"])
            note = ("ход " + str(state["round"]) + ", можно заказать сегодня"
                    if s["sku"] in sim2.orderable(state) else "сегодня поставщик заказы не принимает")
            out.append(";".join(base + [str(state["day"]), sim2._weekday(state["day"]), "",
                                        str(sim2.stock_of(state)[s["sku"]]), str(transit), "", "",
                                        note + (f", в пути {transit}" if transit else "")]))
    for e in sim2.public_events(min(state["day"], sim2.DAYS)):
        out.append(";".join(["_event", e.replace(";", ",")] + [""] * (head.count(";") - 1)))
    return ("﻿" + "\n".join(out) + "\n").encode("utf-8")


AGENT_MD = f"""# Уровень 2 «Супермаркет» — инструкция для ИИ-агента

Ты закупщик супермаркета. {sim2.DAYS} дней (день 1 — понедельник), 10 товаров, 5 поставщиков.
Ход — это день заказа: дни {", ".join(map(str, sim2.ORDER_DAYS))} (пн и чт), всего {sim2.ROUNDS} ходов.
В каждый ход заказать можно только товары поставщиков, которые принимают заказы в этот день недели
(`orderable` в `/api/state`). После заказа мир проживает дни до следующего хода.

{CODE_RULE}

## Правила мира

- Заказ приезжает утром дня «день заказа + плечо поставщика» и продаётся в тот же день.
  Поставщики иногда задерживают поставки без предупреждения.
- Продажи идут партиями, старые первыми. Партия скоропорта списывается вечером последнего дня годности
  (`shelf_days`: молоко 5, фарш 4, йогурт 10 дней).
- Потери за день: нехватка × (цена продажи − закупка) + списание × закупка
  + остаток на вечер × закупка × {sim2.HOLDING_RATE_DAY:.5f}.
- Спрос зависит от дня недели. Новости (промо, погода, задержки) появляются в `events`, когда о них становится известно.
- Продажи в день с пустой полкой (`shelf_empty=1`) ниже настоящего спроса.
- Правила заказа: целые числа ≥ 0, кратно `pack`, не меньше `min_order` (или 0).

## API (база: https://inventory-lab.tsdpu.org)

Ключ участника выдаёт человек; заголовок `Authorization: Bearer ABCD-EFGH`. Тело запросов — JSON в UTF-8.

- `GET /api/state` — день, ход, `orderable`, `stock`, `batches` (партии и последний день годности),
  `in_transit` (заказанное и плановый день прихода), `events`, `world` (поставщики, товары, 28 дней истории),
  `log` (сыгранные дни по товарам).
- `GET /api/export.csv` — всё то же по дням в одной таблице.
- `POST /api/order` — `{{"order": {{"milk": 40, "mince": 12}}, "note": "формула и числа"}}`.
- `GET /api/leaderboard?level=2`.
"""
