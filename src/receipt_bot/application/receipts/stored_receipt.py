from dataclasses import dataclass

from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.receipts.receipt import Receipt


@dataclass(frozen=True)
class StoredReceipt:
    """Атомарно сохранённый чек и текущее состояние всех его задач."""

    receipt: Receipt
    review_tasks: tuple[ReviewTask, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_tasks", tuple(self.review_tasks))
