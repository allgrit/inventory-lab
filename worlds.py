"""Миры уровней 2–4. Механика и API одинаковые (sim2.make_world); различаются товары, спрос и события.

Уровень 2 — тренировочный: попыток сколько угодно, на нём отлаживают программу.
Уровни 3 и 4 — контрольные: одна попытка на имя. Программа, подогнанная под уровень 2, здесь проиграет:
другой seed спроса, другие события и дни, другой товар с дефицитом в истории; на уровне 4 — другой ассортимент.
"""
import copy

import sim2

WD_FLAT = [1.0] * 7
WD_DAIRY = [0.9, 0.9, 0.95, 1.0, 1.1, 1.25, 0.9]
WD_WEEKEND = [0.85, 0.85, 0.9, 1.0, 1.2, 1.35, 1.0]


def _skus(changes):
    skus = copy.deepcopy(sim2.L2_SKUS)
    for s in skus:
        s.update(changes.get(s["sku"], {}))
    return skus


# ---------- Уровень 3 · Контроль A: тот же магазин, другой месяц ----------
L3 = sim2.make_world({
    "title": "Уровень 3 · Контроль A (одна попытка)",
    "seed": 20261103, "noise": 0.28,
    "suppliers": copy.deepcopy(sim2.L2_SUPPLIERS),
    "skus": _skus({"milk": {"base": 21}, "yogurt": {"base": 9, "trend": 0.3}, "mince": {"base": 7},
                   "pasta": {"base": 7}, "buckwheat": {"base": 6, "trend": 0.0}, "water": {"base": 16},
                   "juice": {"base": 7}, "coffee": {"base": 0.9}}),
    "events": [
        {"id": "pasta-promo", "text": "Промо на макароны, дни 8–14: «2 по цене 1,5», в прошлых акциях продажи росли в 1,8–2,5 раза",
         "announce": 1, "days": range(8, 15), "skus": {"pasta": 2.2},
         "info": {"type": "promo", "skus": ["pasta"], "day_from": 8, "day_to": 14, "uplift_range": [1.8, 2.5]}},
        {"id": "cold", "text": "Прогноз: похолодание в дни 10–16, вода и сок обычно продаются на 30–45 % хуже",
         "announce": 4, "days": range(10, 17), "skus": {"water": 0.6, "juice": 0.7},
         "info": {"type": "weather", "skus": ["water", "juice"], "day_from": 10, "day_to": 16,
                  "uplift_range": [0.55, 0.7]}},
        {"id": "dairy-delay", "text": "Молочный комбинат задержал поставку, заказанную в день 11, на 1 день",
         "announce": 12, "days": range(0), "skus": {}, "delay": {"supplier": "dairy", "order_day": 11, "days": 1},
         "info": {"type": "supplier_delay", "supplier": "dairy", "order_day": 11, "delay_days": 1}},
    ],
    "start_stock": {"milk": [(25, 2)], "yogurt": [(18, 6)], "mince": [(6, 2)], "pasta": [(30, None)],
                    "buckwheat": [(36, None)], "oil": [(16, None)], "coffee": [(6, None)], "tea": [(10, None)],
                    "water": [(60, None)], "juice": [(14, None)]},
    "history_trap": {"yogurt": (-6, -4, 3)},
})

# ---------- Уровень 4 · Контроль B: другой ассортимент и больше неопределённости ----------
L4_SUPPLIERS = copy.deepcopy(sim2.L2_SUPPLIERS)
L4_SUPPLIERS["fruit"] = {"name": "Фруктовая база", "order_days": ["пн", "чт"], "lead": 2}
L4_SUPPLIERS["import"]["lead"] = 9
L4_SKUS = [s for s in _skus({"milk": {"base": 24, "shelf": 4}, "mince": {"base": 9, "shelf": 3},
                             "buckwheat": {"base": 4, "trend": -0.3}, "oil": {"base": 5},
                             "coffee": {"base": 1.2}, "water": {"base": 26, "min_order": 72}})
           if s["sku"] not in ("tea", "juice")]
L4_SKUS += [
    {"sku": "cheese", "name": "Сыр 200 г", "supplier": "dairy", "buy": 150, "sell": 230, "shelf": 14,
     "pack": 6, "min_order": 12, "base": 5, "weekday": WD_WEEKEND, "trend": 0.2},
    {"sku": "bananas", "name": "Бананы, кг", "supplier": "fruit", "buy": 95, "sell": 140, "shelf": 5,
     "pack": 1, "min_order": 10, "base": 14, "weekday": WD_WEEKEND, "trend": 0.0},
    {"sku": "apples", "name": "Яблоки, кг", "supplier": "fruit", "buy": 80, "sell": 125, "shelf": 12,
     "pack": 1, "min_order": 10, "base": 9, "weekday": WD_WEEKEND, "trend": 0.0},
]
L4 = sim2.make_world({
    "title": "Уровень 4 · Контроль B (одна попытка)",
    "seed": 20261104, "noise": 0.35,
    "suppliers": L4_SUPPLIERS, "skus": L4_SKUS,
    "events": [
        {"id": "milk-promo", "text": "Промо на молоко, дни 8–10: скидка 25 %, в прошлых акциях продажи росли в 1,5–2,5 раза",
         "announce": 4, "days": range(8, 11), "skus": {"milk": 2.0},
         "info": {"type": "promo", "skus": ["milk"], "day_from": 8, "day_to": 10, "uplift_range": [1.5, 2.5]}},
        {"id": "heat", "text": "Прогноз: жара в дни 12–17, вода обычно продаётся в 1,5–2,5 раза лучше, фрукты — на 20–30 %",
         "announce": 8, "days": range(12, 18), "skus": {"water": 2.1, "bananas": 1.25, "apples": 1.2},
         "info": {"type": "weather", "skus": ["water", "bananas", "apples"], "day_from": 12, "day_to": 17,
                  "uplift_range": [1.2, 2.5]}},
        {"id": "coffee-blogger", "text": "Кофе внезапно стал популярен: продажи выросли",
         "announce": None, "days": range(15, 29), "skus": {"coffee": 2.5},
         "info": {"type": "demand_shift", "skus": ["coffee"]}},
        {"id": "meat-delay", "text": "Мясокомбинат задержал поставку, заказанную в день 18, на 1 день",
         "announce": 19, "days": range(0), "skus": {}, "delay": {"supplier": "meat", "order_day": 18, "days": 1},
         "info": {"type": "supplier_delay", "supplier": "meat", "order_day": 18, "delay_days": 1}},
        {"id": "fruit-delay", "text": "Фруктовая база задержала поставку, заказанную в день 22, на 2 дня",
         "announce": 24, "days": range(0), "skus": {}, "delay": {"supplier": "fruit", "order_day": 22, "days": 2},
         "info": {"type": "supplier_delay", "supplier": "fruit", "order_day": 22, "delay_days": 2}},
    ],
    "start_stock": {"milk": [(30, 2)], "yogurt": [(20, 6)], "mince": [(9, 1)], "pasta": [(40, None)],
                    "buckwheat": [(20, None)], "oil": [(24, None)], "coffee": [(6, None)], "water": [(90, None)],
                    "cheese": [(18, 10)], "bananas": [(20, 2)], "apples": [(25, 8)]},
    "history_trap": {"bananas": (-12, -10, 5), "water": (-4, -3, 12)},
})

WORLDS = {2: sim2.L2, 3: L3, 4: L4}
CONTROL_LEVELS = {3, 4}
