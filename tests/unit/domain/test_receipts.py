from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.money import Money

SAVED_AT = datetime(2026, 10, 22, 12, tzinfo=UTC)
FOOD = Category("food", "Продукты")


def make_item(**changes):
    from receipt_bot.domain.receipts.receipt_item import ReceiptItem

    values = {
        "id": "item-1",
        "item_name": "Чай",
        "item_price": Money(12_345),
        "category": FOOD,
        "created_at": SAVED_AT,
        "updated_at": SAVED_AT,
    }
    values.update(changes)
    return ReceiptItem(**values)


def make_receipt(**changes):
    from receipt_bot.domain.receipts.receipt import Receipt

    values = {
        "id": "receipt-1",
        "owner_id": 123,
        "source_key": "update-1:0",
        "purchase_date": date(2026, 10, 1),
        "total": Money(12_345),
        "items": [make_item()],
    }
    values.update(changes)
    return Receipt(**values)


def test_category_uncertainty_keeps_financially_checked_receipt_in_reports():
    receipt = make_receipt(items=[make_item(category=None)])
    assert receipt.is_reportable is True


@pytest.mark.parametrize(
    "changes",
    [
        {"purchase_date": None},
        {"total": None},
        {"total": Money(12_346)},
        {"items": []},
        {"review_reasons": ("Нечитаемые суммы",)},
    ],
)
def test_incomplete_or_mismatched_receipt_never_becomes_reportable(changes):
    receipt = make_receipt(**changes)
    assert receipt.is_reportable is False


def test_unknown_item_name_or_unresolved_financial_issue_excludes_receipt():
    assert make_receipt(items=[make_item(item_name=None)]).is_reportable is False
    assert make_receipt(items=[make_item(item_price=None)]).is_reportable is False
    assert make_receipt(items=[make_item(review_reasons=("Неясная скидка",))]).is_reportable is False


def test_zero_price_and_separate_purchase_date_are_preserved():
    receipt = make_receipt(total=Money(0), items=[make_item(item_price=Money(0))])
    assert receipt.is_reportable is True
    assert receipt.purchase_date == date(2026, 10, 1)
    assert receipt.items[0].created_at == datetime(2026, 10, 22, 12, tzinfo=UTC)


def test_receipt_defends_its_invariants_against_external_mutation():
    items = [make_item()]
    receipt = make_receipt(items=items)
    items.clear()
    assert len(receipt.items) == 1
    with pytest.raises(FrozenInstanceError):
        receipt.total = Money(0)
