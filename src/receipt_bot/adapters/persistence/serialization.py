from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.money import Money
from receipt_bot.domain.receipts.receipt import Receipt
from receipt_bot.domain.receipts.receipt_item import ReceiptItem


def category_data(category: Category | None) -> dict | None:
    return None if category is None else {"code": category.code, "name": category.name}


def category_model(value: dict | None) -> Category | None:
    return None if value is None else Category(value["code"], value["name"])


def money_units(money: Money | None) -> int | None:
    if money is None:
        return None
    if money.units >= 10**38:
        raise ValueError("Сумма превышает точность хранилища")
    return money.units


def receipt_model(row: dict, items: list[dict]) -> Receipt:
    result = []
    for item in items:
        result.append(
            ReceiptItem(
                item["id"],
                item["item_name"],
                None if item["price"] is None else Money(int(item["price"])),
                category_model(item["category"]),
                item["created_at"],
                item["updated_at"],
                tuple(item["review_reasons"]),
            )
        )
    return Receipt(
        row["id"],
        row["owner_id"],
        row["source_key"],
        row["purchase_date"],
        None if row["total"] is None else Money(int(row["total"])),
        tuple(result),
        tuple(row["review_reasons"]),
    )


def task_model(row: dict) -> ReviewTask:
    return ReviewTask(
        row["id"],
        row["owner_id"],
        row["item_id"],
        tuple(category_model(c) for c in row["options"]),
        row["status"],
        category_model(row["answer"]),
    )
