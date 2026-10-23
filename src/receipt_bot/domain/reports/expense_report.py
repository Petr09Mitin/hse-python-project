from dataclasses import dataclass

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.money import Money
from receipt_bot.domain.reports.expense_report_row import ExpenseReportRow
from receipt_bot.domain.reports.report_period import ReportPeriod


@dataclass(frozen=True)
class ExpenseReport:
    """Подготовленные строки отчёта с вычисляемыми точными итогами."""

    period: ReportPeriod
    rows: tuple[ExpenseReportRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))

    @property
    def total(self) -> Money:
        """Считает точную сумму расходов."""
        total = Money(0)
        for row in self.rows:
            total += row.price
        return total

    @property
    def category_totals(self) -> dict[Category | None, Money]:
        """Считает расходы по категориям, отдельно выделяя неизвестную."""
        totals = {}
        for row in self.rows:
            totals[row.category] = totals.get(row.category, Money(0)) + row.price
        return totals
