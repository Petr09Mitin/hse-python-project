from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData


def receipt_issues(data: StructuredReceiptData) -> tuple[str, ...]:
    """Возвращает причины, по которым чек исключается из расходов."""
    issues = []
    if data.purchase_date is None:
        issues.append("Не удалось прочитать дату покупки")
    if data.total is None:
        issues.append("Не удалось прочитать итог чека")
    if not data.items:
        issues.append("Не найдены позиции чека")
    item_total = Money(0)
    all_prices_known = True
    for index, item in enumerate(data.items, start=1):
        if item.item_name is None:
            issues.append(f"Не удалось прочитать название позиции {index}")
        if item.item_price is None:
            issues.append(f"Не удалось прочитать сумму позиции {index}")
            all_prices_known = False
        else:
            item_total += item.item_price
    if data.total is not None and all_prices_known and data.items and item_total != data.total:
        issues.append("Сумма позиций не совпадает с итогом чека")
    return tuple(issues)
