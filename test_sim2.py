import sim2


def test_oracle_beats_naive_and_nothing():
    oracle, naive = sim2.run_policy(sim2.oracle), sim2.run_policy(sim2.naive)
    nothing = sim2.run_policy(lambda state, last: {})
    assert oracle < naive < nothing


def test_order_rules_by_weekday_pack_and_min():
    state = sim2.new_state()  # день 1, понедельник
    assert "water" not in sim2.orderable(state)  # напитки заказываются по четвергам
    _, errors = sim2.validate_order({"water": 48}, state)
    assert errors
    _, errors = sim2.validate_order({"pasta": 12}, state)
    assert errors  # минимум 24
    clean, errors = sim2.validate_order({"pasta": 24, "milk": 20}, state)
    assert not errors and clean == {"pasta": 24, "milk": 20}


def test_fifo_expiry_writes_off_old_batch():
    state = sim2.new_state()
    state["batches"]["milk"] = [[500, 1]]  # партия годна только в день 1
    state, rep = sim2.play_round(state, {})
    day1 = rep["days"][0]["lines"]["milk"]
    assert day1["written_off"] == 500 - day1["sold"]
    assert rep["days"][1]["lines"]["milk"]["stock_end"] == 0


def test_delivery_arrives_after_lead_time_and_delay_event():
    assert sim2._arrival("milk", 1) == 2
    assert sim2._arrival("pasta", 15) == 15 + 3 + 2  # необъявленная задержка


def test_events_announced_only_from_their_day():
    assert not any("жара" in e for e in sim2.public_events(11))
    assert any("жара" in e.lower() for e in sim2.public_events(15))


def test_history_shows_empty_shelf_only_for_milk_trap():
    empty = {k: [d for d, e in zip(sim2.HISTORY_DAYS, h["stock_end"]) if e == 0] for k, h in sim2.HISTORY.items()}
    assert empty.pop("milk") == [-9, -8, -7]
    assert not any(empty.values())


def test_delay_becomes_visible_in_plan_only_after_announcement():
    p = {"sku": "pasta", "ordered": 15, "planned": 18}
    assert sim2.announced_arrival(p, 15) == (18, False)
    assert sim2.announced_arrival(p, 18) == (20, True)


def test_structured_events_and_history_empty_flag():
    info = {e["id"]: e for e in sim2.public_events_info(15)}
    assert info["oil-promo"]["skus"] == ["oil"] and info["heat"]["day_from"] == 19
    assert "grocery-delay" not in info
    hist = sim2.public_world()["history"]["milk"]
    assert [d for d, e in zip(sim2.HISTORY_DAYS, hist["empty"]) if e] == [-9, -8, -7]


def test_supplier_schedule_next_order_and_arrival():
    sched = sim2.supplier_schedule(1)
    assert sched["drinks"]["next_order_day"] == 4 and sched["drinks"]["planned_arrival"] == 6
    assert sched["import"]["next_order_day"] == 1 and sched["import"]["planned_arrival"] == 8
