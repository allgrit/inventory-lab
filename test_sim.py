import sim


def test_lost_sales_and_writeoff_for_perishable():
    stock, lines = sim.play_round(sim.initial_stock(), {"milk": 100}, 1)
    milk = next(line for line in lines if line["sku"] == "milk")
    assert milk["sold"] == 100 and milk["lost"] == 22
    assert milk["cost_lost"] == 22 * 25 and stock["milk"] == 0

    stock, lines = sim.play_round(sim.initial_stock(), {"milk": 150}, 1)
    milk = next(line for line in lines if line["sku"] == "milk")
    assert milk["written_off"] == 28 and milk["cost_writeoff"] == 28 * 60 and stock["milk"] == 0


def test_order_constraints():
    _, errors = sim.validate_order({"water": 10})
    assert errors  # не кратно 6
    _, errors = sim.validate_order({"water": 18})
    assert errors  # меньше минимума 24
    clean, errors = sim.validate_order({"water": 24, "milk": "7"})
    assert not errors and clean["milk"] == 7 and clean["chips"] == 0


def test_oracle_beats_naive_and_no_order_is_worst():
    oracle, naive = sim.run_policy(sim.oracle), sim.run_policy(sim.naive)
    nothing = sim.run_policy(lambda stock, week, last: {})
    assert oracle < naive < nothing


def test_public_world_hides_future_demand():
    assert all("demand" not in s for s in sim.public_world())
