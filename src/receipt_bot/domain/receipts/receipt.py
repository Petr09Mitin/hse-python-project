from dataclasses import dataclass
from datetime import date

from receipt_bot.domain.money import Money
from receipt_bot.domain.receipts.receipt_item import ReceiptItem


@dataclass(frozen=True)
class Receipt:
    """Сохранённый чек и причины исключения из расходов."""

    id: str
    owner_id: int
    source_key: str
    purchase_date: date | None
    total: Money | None
    items: tuple[ReceiptItem, ...]
    review_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "review_reasons", tuple(self.review_reasons))

    @property
    def is_reportable(self) -> bool:
        """В отчёт допускается только полный чек с точным совпадением сумм."""
        if self.purchase_date is None or self.total is None or not self.items or self.review_reasons:
            return False
        total = Money(0)
        for item in self.items:
            if item.item_name is None or item.item_price is None or item.review_reasons:
                return False
            total += item.item_price
        return total == self.total
