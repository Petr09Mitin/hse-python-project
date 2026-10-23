from dataclasses import dataclass
from datetime import date

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.money import Money


@dataclass(frozen=True)
class ExpenseReportRow:
    """Строка с известными суммой и датой; категория может требовать уточнения."""

    purchase_date: date
    item_name: str
    price: Money
    category: Category | None
