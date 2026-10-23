from dataclasses import dataclass

from receipt_bot.domain.money import Money


@dataclass(frozen=True)
class StructuredItemData:
    """Название и сумма позиции; None означает нечитаемое значение."""

    item_name: str | None
    item_price: Money | None
