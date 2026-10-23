from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportPeriod:
    """Включительный диапазон дат покупки."""

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("Начало периода не может быть позже конца")

    def contains(self, purchase_date: date) -> bool:
        """Проверяет включение календарной даты в период."""
        return self.start_date <= purchase_date <= self.end_date
