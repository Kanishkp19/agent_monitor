from app.discount import shipping_fee


def test_threshold_is_free() -> None:
    assert shipping_fee(50) == 0


def test_above_threshold_is_free() -> None:
    assert shipping_fee(70) == 0


def test_below_threshold_costs_five() -> None:
    assert shipping_fee(49) == 5
