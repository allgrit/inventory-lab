"""Уровень 2 «Супермаркет»: дневные данные, 10 товаров, 5 поставщиков, 8 ходов за 28 дней.

День 1 — понедельник. Заказы делаются в дни заказа поставщика (ход = понедельник или четверг),
приезжают утром дня (заказ + плечо) и продаются в тот же день. Продажи — по партиям, старые первыми (FIFO);
партия, у которой закончился срок, списывается вечером последнего дня годности.
Спрос одинаков для всех игроков: он заранее разыгран с фиксированным seed.
"""
import random

DAYS = 28
ORDER_DAYS = [1, 4, 8, 11, 15, 18, 22, 25]  # пн и чт
ROUNDS = len(ORDER_DAYS)
HOLDING_RATE_DAY = 0.05 / 7
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

SUPPLIERS = {
    "dairy": {"name": "Молочный комбинат", "order_days": ["пн", "чт"], "lead": 1},
    "grocery": {"name": "Дистрибьютор бакалеи", "order_days": ["пн"], "lead": 3},
    "import": {"name": "Импортёр кофе и чая", "order_days": ["пн"], "lead": 7},
    "drinks": {"name": "Поставщик напитков", "order_days": ["чт"], "lead": 2},
    "meat": {"name": "Мясокомбинат", "order_days": ["пн", "чт"], "lead": 1},
}

# base — средний спрос в день; weekday — множители пн..вс; trend — рост за 28 дней
SKUS = [
    {"sku": "milk", "name": "Молоко 2,5% 1 л", "supplier": "dairy", "buy": 60, "sell": 85, "shelf": 5,
     "pack": 1, "min_order": 0, "base": 18, "weekday": [0.9, 0.9, 0.95, 1.0, 1.1, 1.25, 0.9], "trend": 0.0},
    {"sku": "yogurt", "name": "Йогурт питьевой", "supplier": "dairy", "buy": 45, "sell": 70, "shelf": 10,
     "pack": 6, "min_order": 0, "base": 11, "weekday": [0.9, 0.95, 1.0, 1.0, 1.05, 1.2, 0.9], "trend": 0.0},
    {"sku": "mince", "name": "Фарш охлаждённый 400 г", "supplier": "meat", "buy": 180, "sell": 260, "shelf": 4,
     "pack": 1, "min_order": 0, "base": 6, "weekday": [0.8, 0.85, 0.9, 1.0, 1.25, 1.4, 0.8], "trend": 0.0},
    {"sku": "pasta", "name": "Макароны 450 г", "supplier": "grocery", "buy": 55, "sell": 85, "shelf": None,
     "pack": 12, "min_order": 24, "base": 8, "weekday": [1.0] * 7, "trend": 0.0},
    {"sku": "buckwheat", "name": "Гречка 900 г", "supplier": "grocery", "buy": 90, "sell": 135, "shelf": None,
     "pack": 12, "min_order": 24, "base": 5, "weekday": [1.0] * 7, "trend": 0.4},
    {"sku": "oil", "name": "Масло подсолнечное 1 л", "supplier": "grocery", "buy": 110, "sell": 160, "shelf": None,
     "pack": 12, "min_order": 24, "base": 4, "weekday": [1.0] * 7, "trend": 0.0},
    {"sku": "coffee", "name": "Кофе зерновой 1 кг", "supplier": "import", "buy": 900, "sell": 1350, "shelf": None,
     "pack": 6, "min_order": 6, "base": 0.6, "weekday": [1.0] * 7, "trend": 0.0},
    {"sku": "tea", "name": "Чай чёрный 100 пак.", "supplier": "import", "buy": 160, "sell": 240, "shelf": None,
     "pack": 6, "min_order": 6, "base": 1.5, "weekday": [1.0] * 7, "trend": 0.0},
    {"sku": "water", "name": "Вода 0,5 л", "supplier": "drinks", "buy": 25, "sell": 45, "shelf": None,
     "pack": 12, "min_order": 48, "base": 20, "weekday": [0.9, 0.9, 0.95, 1.0, 1.1, 1.3, 1.2], "trend": 0.0},
    {"sku": "juice", "name": "Сок яблочный 1 л", "supplier": "drinks", "buy": 70, "sell": 110, "shelf": None,
     "pack": 6, "min_order": 0, "base": 6, "weekday": [0.9, 0.9, 0.95, 1.0, 1.1, 1.25, 1.1], "trend": 0.0},
]
BY_SKU = {s["sku"]: s for s in SKUS}

# События: announce — день, с которого игрок о нём знает (None — не объявляется)
EVENTS = [
    {"id": "oil-promo", "text": "Промо на масло, дни 15–21: скидка 20 %, в прошлых акциях продажи росли в 2–3 раза",
     "announce": 1, "days": range(15, 22), "skus": {"oil": 2.5},
     "info": {"type": "promo", "skus": ["oil"], "day_from": 15, "day_to": 21, "uplift_range": [2, 3]}},
    {"id": "heat", "text": "Прогноз: жара в дни 19–23, напитки обычно продаются в 1,5–2 раза лучше",
     "announce": 15, "days": range(19, 24), "skus": {"water": 1.8, "juice": 1.4},
     "info": {"type": "weather", "skus": ["water", "juice"], "day_from": 19, "day_to": 23,
              "uplift_range": [1.5, 2]}},
    {"id": "grocery-delay", "text": "Дистрибьютор бакалеи задержал поставку, заказанную в день 15, на 2 дня",
     "announce": 18, "days": range(0), "skus": {}, "delay": {"supplier": "grocery", "order_day": 15, "days": 2},
     "info": {"type": "supplier_delay", "supplier": "grocery", "order_day": 15, "delay_days": 2}},
]


def _weekday(day):
    return WEEKDAYS[(day - 1) % 7]


def _demand_table():
    rng = random.Random(20261102)
    table = {}
    for s in SKUS:
        row = {}
        for day in range(-27, DAYS + 1):
            mean = s["base"] * s["weekday"][(day - 1) % 7] * (1 + s["trend"] * max(day, 0) / DAYS)
            for e in EVENTS:
                if day in e["days"] and s["sku"] in e["skus"]:
                    mean *= e["skus"][s["sku"]]
            if s["base"] < 2:  # редкие продажи: штучные покупки
                row[day] = sum(1 for _ in range(4) if rng.random() < mean / 4)
            else:
                row[day] = max(0, round(rng.gauss(mean, mean * 0.25)))
        table[s["sku"]] = row
    return table


DEMAND = _demand_table()
HISTORY_DAYS = list(range(-27, 1))  # 28 дней до игры: −27 … 0


def _history():
    """Продажи и остатки до игры. У молока в днях −9…−7 полка пустела: продажи ниже спроса."""
    hist = {}
    for s in SKUS:
        sales, ends = [], []
        for d in HISTORY_DAYS:
            dem = DEMAND[s["sku"]][d]
            if s["sku"] == "milk" and -9 <= d <= -7:
                sold, end = min(dem, 6), 0
            else:
                sold, end = dem, max(3, round(s["base"] * 2.5)) + (d % 3)  # полка не пустела
            sales.append(sold)
            ends.append(end)
        hist[s["sku"]] = {"sales": sales, "stock_end": ends}
    return hist


HISTORY = _history()

START_STOCK = {"milk": [(30, 3)], "yogurt": [(24, 7)], "mince": [(8, 2)], "pasta": [(40, None)],
               "buckwheat": [(30, None)], "oil": [(20, None)], "coffee": [(9, None)], "tea": [(14, None)],
               "water": [(70, None)], "juice": [(20, None)]}


def new_state():
    return {"round": 1, "day": ORDER_DAYS[0], "batches": {k: [list(b) for b in v] for k, v in START_STOCK.items()},
            "pending": [], "total": 0}


def finished(state):
    return state["round"] > ROUNDS


def orderable(state):
    """Товары, которые можно заказать в текущий ход."""
    wd = _weekday(state["day"])
    return [s["sku"] for s in SKUS if wd in SUPPLIERS[s["supplier"]]["order_days"]]


def validate_order(order, state):
    clean, errors, allowed = {}, [], set(orderable(state))
    for s in SKUS:
        raw = order.get(s["sku"], 0)
        try:
            q = int(raw)
        except (TypeError, ValueError):
            errors.append(f"{s['name']}: нужно целое число")
            continue
        if q < 0 or q > 5000:
            errors.append(f"{s['name']}: от 0 до 5000")
        elif q and s["sku"] not in allowed:
            errors.append(f"{s['name']}: сегодня ({_weekday(state['day'])}) поставщик заказы не принимает")
        elif q and q % s["pack"]:
            errors.append(f"{s['name']}: кратно {s['pack']} шт.")
        elif q and q < s["min_order"]:
            errors.append(f"{s['name']}: минимум {s['min_order']} шт.")
        if q and not errors:
            clean[s["sku"]] = q
    return clean, errors


def _arrival(sku, order_day):
    sup = BY_SKU[sku]["supplier"]
    day = order_day + SUPPLIERS[sup]["lead"]
    for e in EVENTS:
        d = e.get("delay")
        if d and d["supplier"] == sup and d["order_day"] == order_day:
            day += d["days"]
    return day


def stock_of(state):
    return {k: sum(q for q, _ in v) for k, v in state["batches"].items()}


def play_round(state, order):
    """Принимает заказ текущего хода и проживает дни до следующего хода. Возвращает (state, отчёт)."""
    state = {**state, "batches": {k: [list(b) for b in v] for k, v in state["batches"].items()},
             "pending": [dict(p) for p in state["pending"]]}
    start = state["day"]
    for sku, q in order.items():
        planned = start + SUPPLIERS[BY_SKU[sku]["supplier"]]["lead"]  # то, что знает игрок; задержка скрыта
        state["pending"].append({"sku": sku, "qty": q, "day": _arrival(sku, start), "ordered": start,
                                 "planned": planned})
    end = ORDER_DAYS[state["round"]] - 1 if state["round"] < ROUNDS else DAYS
    days, cost = [], {"lost": 0, "writeoff": 0, "holding": 0}
    for day in range(start, end + 1):
        lines = {}
        for s in SKUS:
            k, batches = s["sku"], state["batches"][s["sku"]]
            arrived = 0
            for p in [p for p in state["pending"] if p["sku"] == k and p["day"] == day]:
                expiry = day + s["shelf"] - 1 if s["shelf"] else None
                batches.append([p["qty"], expiry])
                arrived += p["qty"]
                state["pending"].remove(p)
            batches.sort(key=lambda b: b[1] if b[1] is not None else 10 ** 6)
            dem, need = DEMAND[k][day], DEMAND[k][day]
            for b in batches:
                take = min(b[0], need)
                b[0] -= take
                need -= take
            sold, lost = dem - need, need
            written = sum(b[0] for b in batches if b[1] is not None and b[1] <= day)
            batches[:] = [b for b in batches if b[0] > 0 and (b[1] is None or b[1] > day)]
            left = sum(b[0] for b in batches)
            c_lost = lost * (s["sell"] - s["buy"])
            c_wo = written * s["buy"]
            c_hold = left * s["buy"] * HOLDING_RATE_DAY
            cost["lost"] += c_lost
            cost["writeoff"] += c_wo
            cost["holding"] += c_hold
            lines[k] = {"arrived": arrived, "sold": sold, "stock_end": left, "written_off": written,
                        "empty": lost > 0, "cost": round(c_lost + c_wo + c_hold)}
        days.append({"day": day, "weekday": _weekday(day), "lines": lines})
    total = round(cost["lost"] + cost["writeoff"] + cost["holding"])
    state["total"] += total
    state["round"] += 1
    state["day"] = ORDER_DAYS[state["round"] - 1] if state["round"] <= ROUNDS else DAYS + 1
    report = {"round": state["round"] - 1, "from": start, "to": end, "order": order, "days": days,
              "cost": total, "cost_parts": {k: round(v) for k, v in cost.items()}}
    return state, report


def public_events(day):
    return [e["text"] for e in EVENTS if e["announce"] is not None and e["announce"] <= day]


def public_events_info(day):
    """То же, что public_events, но структурно: тип, товары, дни, диапазон множителя, поставщик."""
    return [{"id": e["id"], "text": e["text"], "announced_day": e["announce"], **e["info"]}
            for e in EVENTS if e["announce"] is not None and e["announce"] <= day]


def announced_arrival(p, day):
    """Плановый день прихода, каким его знает игрок: задержка видна с момента объявления."""
    for e in EVENTS:
        d = e.get("delay")
        if (d and e["announce"] <= day and d["order_day"] == p["ordered"]
                and d["supplier"] == BY_SKU[p["sku"]]["supplier"]):
            return p["planned"] + d["days"], True
    return p["planned"], False


def supplier_schedule(day):
    """Для каждого поставщика: ближайший день заказа (≥ day) и плановый приход такого заказа."""
    out = {}
    for code, sup in SUPPLIERS.items():
        nxt = next((d for d in ORDER_DAYS if d >= day and _weekday(d) in sup["order_days"]), None)
        out[code] = {"next_order_day": nxt, "planned_arrival": nxt + sup["lead"] if nxt else None,
                     "order_days": sup["order_days"], "lead": sup["lead"]}
    return out


def public_world():
    return {"days": DAYS, "order_days": ORDER_DAYS, "holding_rate_day": HOLDING_RATE_DAY,
            "suppliers": SUPPLIERS,
            "skus": [{k: s[k] for k in ("sku", "name", "supplier", "buy", "sell", "shelf", "pack", "min_order")}
                     for s in SKUS],
            "history_days": HISTORY_DAYS,
            "history": {k: {**h, "empty": [1 if e == 0 else 0 for e in h["stock_end"]]}
                        for k, h in HISTORY.items()}}


# ---------- опорные политики ----------

def _next_arrival_after(sku, day):
    for d in ORDER_DAYS:
        if d > day and _weekday(d) in SUPPLIERS[BY_SKU[sku]["supplier"]]["order_days"]:
            return _arrival(sku, d)
    return DAYS + 1


def _fit(sku, need):
    s = BY_SKU[sku]
    if need <= 0:
        return 0
    q = -(-need // s["pack"]) * s["pack"]
    return max(q, s["min_order"])


def oracle(state):
    """Знает будущий спрос и задержки: везёт ровно на период до следующего прихода."""
    order = {}
    for k in orderable(state):
        s, day = BY_SKU[k], state["day"]
        arrive = _arrival(k, day)
        nxt = min(_next_arrival_after(k, day), DAYS + 1)
        if s["shelf"]:
            nxt = min(nxt, arrive + s["shelf"])
        # проекция остатка к дню прихода по известному спросу, с учётом сроков и уже заказанного
        batches = [list(b) for b in state["batches"][k]]
        pend = [p for p in state["pending"] if p["sku"] == k]
        for d in range(day, nxt):
            for p in pend:
                if p["day"] == d:
                    batches.append([p["qty"], d + s["shelf"] - 1 if s["shelf"] else None])
            if d == arrive:
                break
            need = DEMAND[k][d]
            batches.sort(key=lambda b: b[1] if b[1] is not None else 10 ** 6)
            for b in batches:
                t = min(b[0], need)
                b[0] -= t
                need -= t
            batches = [b for b in batches if b[0] > 0 and (b[1] is None or b[1] > d)]
        usable = sum(b[0] for b in batches if b[1] is None or b[1] >= nxt - 1)
        demand = sum(DEMAND[k][d] for d in range(arrive, min(nxt, DAYS + 1)))
        order[k] = _fit(k, demand - usable)
    return order


def naive(state, last_sales):
    """Заказать столько, сколько продали за такое же число прошлых дней, не глядя на остаток."""
    order = {}
    for k in orderable(state):
        nxt = _next_arrival_after(k, state["day"])
        span = max(1, nxt - _arrival(k, state["day"]))
        order[k] = _fit(k, sum(last_sales[k][-span:]))
    return order


def run_policy(policy):
    state = new_state()
    last = {k: list(HISTORY[k]["sales"]) for k in BY_SKU}
    while not finished(state):
        order = policy(state) if policy is oracle else policy(state, last)
        clean, errors = validate_order(order, state)
        assert not errors, errors
        state, rep = play_round(state, clean)
        for d in rep["days"]:
            for k, line in d["lines"].items():
                last[k].append(line["sold"])
    return state["total"]
