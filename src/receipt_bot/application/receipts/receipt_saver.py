from datetime import UTC, datetime
from uuid import uuid4

from receipt_bot.application.receipts.expense_repository import ExpenseRepository
from receipt_bot.application.receipts.stored_receipt import StoredReceipt
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES, Category
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.receipts.receipt import Receipt
from receipt_bot.domain.receipts.receipt_item import ReceiptItem
from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData


class ReceiptSaver:
    """Сохраняет чек, его позиции и вопросы об уточнении категорий."""

    def __init__(self, repository: ExpenseRepository, categories: tuple[Category, ...] = DEFAULT_CATEGORIES):
        self.repository = repository
        self.categories = tuple(categories)

    def save(
        self,
        owner_id: int,
        source_key: str,
        data: StructuredReceiptData,
        categories: tuple[Category | None, ...],
        issues: tuple[str, ...],
    ) -> StoredReceipt:
        if issues:
            categories = (None,) * len(data.items)
        now = datetime.now(UTC)
        items = []
        tasks = []
        for item_data, category in zip(data.items, categories, strict=True):
            item = ReceiptItem(str(uuid4()), item_data.item_name, item_data.item_price, category, now, now)
            items.append(item)
            if category is None and not issues:
                tasks.append(ReviewTask(str(uuid4()), owner_id, item.id, self.categories))
        receipt = Receipt(str(uuid4()), owner_id, source_key, data.purchase_date, data.total, tuple(items), issues)
        return self.repository.save(receipt, tuple(tasks))
