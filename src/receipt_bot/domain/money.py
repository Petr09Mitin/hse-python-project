"""Точные суммы расходов."""

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Money:
    """Сумма: 10 000 целых единиц равны одному рублю."""

    units: int

    def __post_init__(self) -> None:
        if not isinstance(self.units, int) or isinstance(self.units, bool):
            raise TypeError("Денежные единицы должны быть целым числом")
        if self.units < 0:
            raise ValueError("Сумма расхода не может быть отрицательной")

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.units + other.units)
