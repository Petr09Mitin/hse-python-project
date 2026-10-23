from dataclasses import dataclass
from datetime import datetime

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.money import Money


@dataclass(frozen=True)
class ReceiptItem:
    """Позиция после скидок; неизвестные значения представлены None."""

    id: str
    item_name: str | None
    item_price: Money | None
    category: Category | None
    created_at: datetime
    updated_at: datetime
    review_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_reasons", tuple(self.review_reasons))
