"""Учебный мир «Магазин у дома»: 4 товара, 4 недельных раунда, одинаковый спрос для всех игроков.

Порядок раунда: игрок видит остатки и историю → заказывает → заказ приезжает в начале
следующей недели → проигрывается спрос недели → считаются потери в рублях.
"""

ROUNDS = 4
HOLDING_RATE = 0.05  # доля закупочной цены за неделю хранения: деньги на полке и место

SKUS = [
    {"sku": "milk", "name": "Молоко 2,5% 1 л", "unit": "шт", "buy": 60, "sell": 85,
     "perishable": True, "pack": 1, "min_order": 0, "stock": 0,
     "demand": [122, 127, 118, 131],
     "history_sales": [121, 117, 66, 124], "history_stock_end": [4, 2, 0, 3],
     "note": "Годность 7 дней: всё, что не продано за неделю, списывается."},
    {"sku": "chips", "name": "Чипсы 150 г", "unit": "шт", "buy": 70, "sell": 120,
     "perishable": False, "pack": 1, "min_order": 0, "stock": 45,
     "demand": [31, 29, 93, 30],
     "history_sales": [31, 28, 33, 30], "history_stock_end": [52, 49, 46, 45],
     "note": "Промоакция в неделе 3 — объявлена заранее. В прошлых акциях продажи росли в 2,5–3,5 раза."},
    {"sku": "water", "name": "Вода 0,5 л", "unit": "шт", "buy": 25, "sell": 45,
     "perishable": False, "pack": 6, "min_order": 24, "stock": 30,
     "demand": [26, 23, 25, 27],
     "history_sales": [25, 23, 26, 24], "history_stock_end": [31, 32, 30, 30],
     "note": "Поставщик продаёт упаковками по 6 шт., минимум 24 шт."},
    {"sku": "coffee", "name": "Кофе зерновой 1 кг", "unit": "шт", "buy": 600, "sell": 900,
     "perishable": False, "pack": 1, "min_order": 0, "stock": 18,
     "demand": [0, 1, 0, 0],
     "history_sales": [1, 0, 0, 0], "history_stock_end": [19, 19, 18, 18],
     "note": "Дорогой товар с редкими продажами. Остаток нельзя вернуть поставщику или уценить."},
]
PROMO = {"chips": [3]}
BY_SKU = {s["sku"]: s for s in SKUS}


def validate_order(order):
    """Возвращает (нормализованный заказ, список ошибок)."""
    clean, errors = {}, []
    for s in SKUS:
        raw = order.get(s["sku"], 0)
        try:
            q = int(raw)
        except (TypeError, ValueError):
            errors.append(f"{s['name']}: нужно целое число")
            continue
        if q < 0 or q > 2000:
            errors.append(f"{s['name']}: от 0 до 2000")
        elif q and q % s["pack"]:
            errors.append(f"{s['name']}: кратно {s['pack']} шт.")
        elif q and q < s["min_order"]:
            errors.append(f"{s['name']}: минимум {s['min_order']} шт.")
        clean[s["sku"]] = q
    return clean, errors


def play_round(stock, order, week):
    """Проигрывает неделю week (1..ROUNDS). Возвращает (новые остатки, строки по товарам)."""
    new_stock, lines = {}, []
    for s in SKUS:
        k = s["sku"]
        available = stock[k] + order.get(k, 0)
        demand = s["demand"][week - 1]
        sold = min(demand, available)
        left = available - sold
        lost = demand - sold
        written_off = left if s["perishable"] else 0
        left -= written_off
        cost_lost = lost * (s["sell"] - s["buy"])
        cost_writeoff = written_off * s["buy"]
        cost_holding = round(left * s["buy"] * HOLDING_RATE)
        new_stock[k] = left
        lines.append({"sku": k, "name": s["name"], "arrived": order.get(k, 0), "demand": demand,
                      "sold": sold, "lost": lost, "written_off": written_off, "stock_end": left,
                      "cost_lost": cost_lost, "cost_writeoff": cost_writeoff,
                      "cost_holding": cost_holding,
                      "cost": cost_lost + cost_writeoff + cost_holding})
    return new_stock, lines


def initial_stock():
    return {s["sku"]: s["stock"] for s in SKUS}


def run_policy(policy):
    """Проигрывает все раунды политикой policy(stock, week, last_sales) -> order. Итог потерь, ₽."""
    stock, total = initial_stock(), 0
    last = {s["sku"]: s["history_sales"][-1] for s in SKUS}
    for week in range(1, ROUNDS + 1):
        order, errors = validate_order(policy(stock, week, last))
        assert not errors, errors
        stock, lines = play_round(stock, order, week)
        total += sum(line["cost"] for line in lines)
        last = {line["sku"]: line["sold"] for line in lines}
    return total


def _fit(sku, need):
    s = BY_SKU[sku]
    if need <= 0:
        return 0
    q = -(-need // s["pack"]) * s["pack"]
    return max(q, s["min_order"])


def naive(stock, week, last):
    """Заказать столько, сколько продали на прошлой неделе (без учёта остатка и промо)."""
    return {k: _fit(k, v) for k, v in last.items()}


def oracle(stock, week, last):
    """Знает будущий спрос: довозит ровно недостающее."""
    return {s["sku"]: _fit(s["sku"], s["demand"][week - 1] - stock[s["sku"]]) for s in SKUS}


def public_world():
    """Что видит игрок: без будущего спроса."""
    return [{k: v for k, v in s.items() if k not in ("demand", "stock")} | {"promo_weeks": PROMO.get(s["sku"], [])}
            for s in SKUS]
