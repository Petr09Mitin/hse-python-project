import pytest


def test_addition_keeps_a_hundredth_of_a_kopeck_and_large_integer_precision():
    from receipt_bot.domain.money import Money

    first = Money(10_000)
    assert (first + Money(1)).units == 10_001
    assert (Money(10**30) + Money(1)).units == 1_000_000_000_000_000_000_000_000_000_001
    assert first.units == 10_000


@pytest.mark.parametrize("units", [True, False, 1.0, "1", None])
def test_money_rejects_non_integer_units(units):
    from receipt_bot.domain.money import Money

    with pytest.raises(TypeError):
        Money(units)


def test_money_rejects_negative_expenses_but_accepts_zero():
    from receipt_bot.domain.money import Money

    assert Money(0).units == 0
    with pytest.raises(ValueError):
        Money(-1)
