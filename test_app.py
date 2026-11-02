import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request

os.environ["STAND_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import app  # noqa: E402

app.init_db()
SERVER = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SERVER.server_port}"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    try:
        r = OPENER.open(req, timeout=5)
        raw = r.read()
        return r.status, (json.loads(raw) if "json" in r.headers["Content-Type"] else raw.decode("utf-8-sig"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_short_token_resume_export_and_agent_doc():
    assert call("/api/start", {"name": "Аня", "code": "нет"})[0] == 403
    status, j = call("/api/start", {"name": "Аня", "code": "Запасы"})
    token = j["token"]
    assert status == 200 and re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", token)

    status, state = call("/api/resume", {"token": token.lower().replace("-", "")})
    assert status == 200 and state["name"] == "Аня" and state["token"] == token
    assert call("/api/resume", {"token": "ZZZZ-ZZZZ"})[0] == 404

    call("/api/order", {"order": {"milk": 120}}, token)
    status, csv = call(f"/api/export.csv?token={token}")
    rows = csv.strip().split("\n")
    assert status == 200 and rows[0].startswith("sku;")
    assert all(len(r.split(";")) == len(rows[0].split(";")) for r in rows)
    assert "demand" not in csv and any(";сыграно" in r for r in rows)

    status, doc = call("/agent.md")
    assert status == 200 and "Authorization: Bearer" in doc


def test_cp1251_body_and_world_without_start_stock():
    token = call("/api/start", {"name": "Кодировка", "code": "запасы"})[1]["token"]
    req = urllib.request.Request(BASE + "/api/order", headers={"Authorization": "Bearer " + token},
                                 data=json.dumps({"order": {"milk": 120}, "note": "молоко"},
                                                 ensure_ascii=False).encode("cp1251"))
    state = json.loads(OPENER.open(req, timeout=5).read())
    assert state["week"] == 2 and state["log"][0]["note"] == "молоко"
    assert all("stock" not in w for w in state["world"])


def test_csv_marks_promo_week_and_conditions():
    token = call("/api/start", {"name": "Промо", "code": "запасы"})[1]["token"]
    for _ in range(2):
        call("/api/order", {"order": {}}, token)
    rows = call(f"/api/export.csv?token={token}")[1].strip().split("\n")
    head = rows[0].split(";")
    chips_now = [dict(zip(head, r.split(";"))) for r in rows if r.startswith("chips;") and "нужен заказ" in r][0]
    assert chips_now["week"] == "3" and chips_now["promo"] == "1" and "ПРОМО" in chips_now["note"]
    assert "2,5–3,5" in chips_now["conditions"]


def test_level2_game_flow_csv_and_separate_leaderboard():
    token = call("/api/start", {"name": "Уровень2", "code": "запасы", "level": 2})[1]["token"]
    status, st = call("/api/state", token=token)
    assert status == 200 and st["level"] == 2 and st["day"] == 1 and "water" not in st["orderable"]
    assert call("/api/order", {"order": {"water": 48}}, token)[0] == 400
    status, st = call("/api/order", {"order": {"milk": 20, "pasta": 24}}, token)
    assert status == 200 and st["round"] == 2 and st["day"] == 4
    assert {p["sku"] for p in st["in_transit"]} == {"pasta"}  # молоко уже приехало, бакалея едет 3 дня
    csv = call(f"/api/export.csv?token={token}")[1]
    assert "день" not in csv.split("\n")[0] and ";сыграно" in csv and "shelf_empty" in csv
    for _ in range(7):
        call("/api/order", {"order": {}}, token)
    assert call("/api/state", token=token)[1]["finished"]
    names2 = [r["name"] for r in call("/api/leaderboard?level=2")[1]]
    names1 = [r["name"] for r in call("/api/leaderboard?level=1")[1]]
    assert "Уровень2" in names2 and "Уровень2" not in names1


def test_level2_delay_shown_in_transit_from_announcement_day():
    token = call("/api/start", {"name": "Задержка", "code": "запасы", "level": 2})[1]["token"]
    for _ in range(4):
        call("/api/order", {"order": {}}, token)
    st = call("/api/order", {"order": {"pasta": 24}}, token)[1]  # ход в день 15
    pasta = [p for p in st["in_transit"] if p["sku"] == "pasta"][0]
    # день 18 — день объявления задержки: план сдвинут, настоящий день прихода (поле day) не раскрывается
    assert st["day"] == 18 and pasta["planned_day"] == 20 and pasta["delay_announced"] and "day" not in pasta
    assert any(e["type"] == "supplier_delay" for e in st["events_info"])


def test_control_levels_one_attempt_per_name_and_retry_only_on_training():
    first = call("/api/start", {"name": "Контроль Ёж", "code": "запасы", "level": 3})
    assert first[0] == 200 and call("/api/state", token=first[1]["token"])[1]["control"] is True
    again = call("/api/start", {"name": "  контроль  еж ", "code": "запасы", "level": 3})
    assert again[0] == 409 and "одна попытка" in again[1]["error"]
    assert call("/api/start", {"name": "Контроль Ёж", "code": "запасы", "level": 4})[0] == 200
    assert call("/api/retry", {}, first[1]["token"])[0] == 409

    tok = call("/api/start", {"name": "Тренер", "code": "запасы", "level": 2})[1]["token"]
    for _ in range(8):
        call("/api/order", {"order": {}}, tok)
    status, new = call("/api/retry", {}, tok)
    assert status == 200 and new["token"] != tok and new["level"] == 2
    for _ in range(8):
        call("/api/order", {"order": {"milk": 30}}, new["token"])
    rows = [r for r in call("/api/leaderboard?level=2")[1] if r["name"] == "Тренер"]
    assert len(rows) == 1 and rows[0]["attempts"] == 2


def test_level4_has_other_assortment_and_agent_doc_mentions_control():
    tok = call("/api/start", {"name": "Ассортимент", "code": "запасы", "level": 4})[1]["token"]
    skus = {s["sku"] for s in call("/api/state", token=tok)[1]["world"]["skus"]}
    assert {"bananas", "cheese"} <= skus and "tea" not in skus
    doc = call("/agent.md?level=4")[1]
    assert "одна попытка" in doc and "кодом" in doc and "leaderboard?level=4" in doc
