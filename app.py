"""Учебный стенд «Магазин у дома»: HTTP API + страница игрока. Только стандартная библиотека."""
import json
import os
import secrets
import sqlite3
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import sim

DB = Path(os.environ.get("STAND_DB", "stand.db"))
CODE = os.environ.get("STAND_CODE", "запасы")
PAGE = (Path(__file__).parent / "index.html").read_bytes()
LOCK = threading.Lock()
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # без 0/O, 1/I/L


def new_token():
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def norm_token(t):
    t = "".join(ch for ch in str(t).upper() if ch.isalnum())
    return t[:4] + "-" + t[4:8] if len(t) == 8 else ""


def db():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""create table if not exists games(
            id text primary key, name text not null, week integer not null,
            stock text not null, total integer not null, log text not null,
            created text default current_timestamp)""")


def game_view(row):
    log = json.loads(row["log"])
    return {"token": row["id"], "name": row["name"], "week": row["week"], "rounds": sim.ROUNDS,
            "finished": row["week"] > sim.ROUNDS, "stock": json.loads(row["stock"]),
            "total": row["total"], "log": log, "world": sim.public_world(),
            "holding_rate": sim.HOLDING_RATE}


def leaderboard():
    with db() as con:
        rows = con.execute("select name, total, week from games where week > ? order by total limit 50",
                           (sim.ROUNDS,)).fetchall()
    board = [{"name": r["name"], "total": r["total"], "kind": "player"} for r in rows]
    board += [{"name": "Оракул (знает будущее)", "total": sim.run_policy(sim.oracle), "kind": "ref"},
              {"name": "Наивная: заказ = прошлые продажи", "total": sim.run_policy(sim.naive), "kind": "ref"}]
    return sorted(board, key=lambda r: r["total"])


def export_csv(row):
    """Всё, что видит игрок к текущему моменту: условия, история продаж и остатков, текущий остаток."""
    out = ["sku;name;unit;buy;sell;pack;min_order;perishable;conditions;week;promo;sales;stock_end;arrived;note"]
    cur = row["week"]
    log = json.loads(row["log"])
    for s in sim.public_world():
        base = [s["sku"], s["name"], s["unit"], str(s["buy"]), str(s["sell"]), str(s["pack"]),
                str(s["min_order"]), "1" if s["perishable"] else "0",
                s["note"].replace(";", ",")]
        promo = lambda w: "1" if w in s["promo_weeks"] else "0"  # noqa: E731
        for i, (sold, end) in enumerate(zip(s["history_sales"], s["history_stock_end"])):
            out.append(";".join(base + [str(i - 4), "0", str(sold), str(end), "", "история до игры"]))
        for entry in log:
            line = next(x for x in entry["lines"] if x["sku"] == s["sku"])
            out.append(";".join(base + [str(entry["week"]), promo(entry["week"]), str(line["sold"]), str(line["stock_end"]),
                                        str(line["arrived"]), "сыграно"]))
        status = "игра окончена" if cur > sim.ROUNDS else (
            "остаток сейчас, нужен заказ на эту неделю" + (", ПРОМО на эту неделю" if promo(cur) == "1" else ""))
        out.append(";".join(base + [str(cur), promo(cur), "", str(json.loads(row["stock"])[s["sku"]]), "", status]))
    return ("﻿" + "\n".join(out) + "\n").encode("utf-8")


AGENT_MD = f"""# Учебный стенд «Магазин у дома» — инструкция для ИИ-агента

Ты закупщик магазина. {sim.ROUNDS} недели, 4 товара. Каждый ход: заказ → он приезжает к началу недели →
приходит спрос → считаются потери в рублях. Цель — минимальные суммарные потери.

Потери: нехватка = упущенная маржа (продажа − закупка) за штуку; молоко портится за неделю — всё непроданное
списывается по закупочной цене; остаток на конец недели стоит {int(sim.HOLDING_RATE*100)}% закупочной цены.
Будущий спрос не известен. Продажи при пустой полке (остаток 0) занижают спрос.

## API (база: https://inventory-lab.tsdpu.org)

Ключ участника выдаёт человек (вида ABCD-EFGH). Передавай его заголовком `Authorization: Bearer ABCD-EFGH`.

- `GET /api/state` — неделя, остатки, история, условия товаров (`world`).
- `GET /api/export.csv` — то же в CSV.
- `POST /api/order` с JSON `{{"order": {{"milk": 120, "chips": 30, "water": 24, "coffee": 0}}, "note": "почему"}}`
  — заказ на текущую неделю; ответ — новое состояние и итог недели в `log`.
- `GET /api/leaderboard` — таблица.

Правила заказа: целые числа ≥ 0; вода кратно 6 и не меньше 24 (или 0). Не указанный товар = 0.
`note` необязателен, но полезен: коротко объясни, почему такое количество.

Где что лежит в `/api/state`: текущий остаток — `stock`; `world[].history_*` — 4 недели ДО начала игры;
сыгранные недели — `log` (продано, остаток на конец, списано, потери). Хранение начисляется на остаток
на конец недели — после продаж и списаний. Тело запроса — JSON в UTF-8.
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "stand/1"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", cookie=None, disposition=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(data)

    def game_id(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return norm_token(auth[7:])
        q = parse_qs(urlsplit(self.path).query).get("token")
        if q:
            return norm_token(q[0])
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return norm_token(c["game"].value) if "game" in c else None

    def load(self):
        gid = self.game_id()
        if not gid:
            return None
        with db() as con:
            return con.execute("select * from games where id=?", (gid,)).fetchone()

    def cookie(self, gid):
        c = f"game={gid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
        return c + "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else c

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 10000:
            raise ValueError("too large")
        raw = self.rfile.read(n) or b"{}"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1251")  # curl из консоли Windows шлёт тело в локальной кодировке
        return json.loads(text)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if path == "/health":
            return self.send(200, {"status": "ok", "ready": True, "rounds": sim.ROUNDS})
        if path == "/api/world":
            return self.send(200, {"world": sim.public_world(), "rounds": sim.ROUNDS,
                                   "holding_rate": sim.HOLDING_RATE})
        if path == "/agent.md":
            return self.send(200, AGENT_MD.encode(), "text/markdown; charset=utf-8")
        if path == "/api/export.csv":
            row = self.load()
            if not row:
                return self.send(401, {"error": "Нужен ключ участника: ?token=XXXX-XXXX"})
            return self.send(200, export_csv(row), "text/csv; charset=utf-8",
                             disposition=f'attachment; filename="shop-{row["id"]}-week{row["week"]}.csv"')
        if path == "/api/leaderboard":
            return self.send(200, leaderboard())
        if path == "/api/state":
            row = self.load()
            return self.send(200, game_view(row)) if row else self.send(401, {"error": "Сначала войдите"})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            data = self.body()
        except Exception:
            return self.send(400, {"error": "Тело запроса должно быть JSON-объектом, например {\"order\": {\"milk\": 120}}"})
        if path == "/api/start":
            name = str(data.get("name", "")).strip()[:40]
            if not name:
                return self.send(400, {"error": "Введите имя"})
            if str(data.get("code", "")).strip().lower() != CODE:
                return self.send(403, {"error": "Неверное кодовое слово"})
            with LOCK, db() as con:
                gid = new_token()
                while con.execute("select 1 from games where id=?", (gid,)).fetchone():
                    gid = new_token()
                con.execute("insert into games(id,name,week,stock,total,log) values(?,?,?,?,?,?)",
                            (gid, name, 1, json.dumps(sim.initial_stock()), 0, "[]"))
            return self.send(200, {"token": gid, "game_id": gid, "name": name}, cookie=self.cookie(gid))
        if path == "/api/resume":
            gid = norm_token(data.get("token", ""))
            with db() as con:
                row = con.execute("select * from games where id=?", (gid,)).fetchone() if gid else None
            if not row:
                return self.send(404, {"error": "Ключ не найден"})
            return self.send(200, game_view(row), cookie=self.cookie(gid))
        if path == "/api/order":
            with LOCK:
                row = self.load()
                if not row:
                    return self.send(401, {"error": "Сначала войдите"})
                if row["week"] > sim.ROUNDS:
                    return self.send(409, {"error": "Игра окончена"})
                order, errors = sim.validate_order(data.get("order", {}))
                if errors:
                    return self.send(400, {"error": "; ".join(errors)})
                week = row["week"]
                stock, lines = sim.play_round(json.loads(row["stock"]), order, week)
                cost = sum(line["cost"] for line in lines)
                log = json.loads(row["log"]) + [{"week": week, "order": order,
                                                 "note": str(data.get("note", ""))[:300],
                                                 "lines": lines, "cost": cost}]
                with db() as con:
                    con.execute("update games set week=?, stock=?, total=?, log=? where id=?",
                                (week + 1, json.dumps(stock), row["total"] + cost,
                                 json.dumps(log, ensure_ascii=False), row["id"]))
                    row = con.execute("select * from games where id=?", (row["id"],)).fetchone()
            return self.send(200, game_view(row))
        self.send(404, {"error": "not found"})


def main():
    init_db()
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
