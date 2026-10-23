from dataclasses import dataclass
from datetime import date

from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData


@dataclass(frozen=True)
class StructuredReceiptData:
    """Данные до предметной проверки; неизвестные поля сохраняются как None."""

    purchase_date: date | None
    total: Money | None
    items: tuple[StructuredItemData, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
