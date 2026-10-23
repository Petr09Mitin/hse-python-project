from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.money import Money


def test_report_period_includes_both_purchase_date_boundaries_and_one_day():
    from receipt_bot.domain.reports.report_period import ReportPeriod

    period = ReportPeriod(date(2026, 10, 1), date(2026, 10, 22))
    assert period.contains(date(2026, 10, 1)) is True
    assert period.contains(date(2026, 10, 22)) is True
    assert period.contains(date(2026, 9, 30)) is False
    assert period.contains(date(2026, 10, 23)) is False
    assert ReportPeriod(date(2026, 10, 1), date(2026, 10, 1)).contains(date(2026, 10, 1)) is True


def test_report_period_rejects_reversed_dates():
    from receipt_bot.domain.reports.report_period import ReportPeriod

    with pytest.raises(ValueError):
        ReportPeriod(date(2026, 10, 22), date(2026, 10, 1))


def test_report_derives_exact_totals_and_keeps_unclassified_expenses_in_own_group():
    from receipt_bot.domain.reports.expense_report import ExpenseReport
    from receipt_bot.domain.reports.expense_report_row import ExpenseReportRow
    from receipt_bot.domain.reports.report_period import ReportPeriod

    food = Category("food", "Продукты")
    rows = [
        ExpenseReportRow(date(2026, 10, 1), "Чай", Money(10**30), food),
        ExpenseReportRow(date(2026, 10, 22), "Хлеб", Money(2), food),
        ExpenseReportRow(date(2026, 10, 3), "Новая покупка", Money(1), None),
    ]
    report = ExpenseReport(ReportPeriod(date(2026, 10, 1), date(2026, 10, 22)), rows)
    rows.clear()
    assert len(report.rows) == 3
    assert report.total.units == 1_000_000_000_000_000_000_000_000_000_003
    assert report.category_totals == {food: Money(1_000_000_000_000_000_000_000_000_000_002), None: Money(1)}
    report.category_totals.clear()
    assert report.category_totals[None] == Money(1)
    with pytest.raises(FrozenInstanceError):
        report.rows = ()


def test_empty_report_has_exact_zero_total_and_no_groups():
    from receipt_bot.domain.reports.expense_report import ExpenseReport
    from receipt_bot.domain.reports.report_period import ReportPeriod

    report = ExpenseReport(ReportPeriod(date(2026, 10, 1), date(2026, 10, 22)), [])
    assert report.total == Money(0)
    assert report.category_totals == {}
