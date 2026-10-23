from dataclasses import dataclass

from receipt_bot.domain.categories.category import Category


@dataclass(frozen=True)
class ReviewTask:
    """Однократное уточнение категории позиции заданного владельца."""

    id: str
    owner_id: int
    item_id: str
    options: tuple[Category, ...]
    status: str = "pending"
    answer_category: Category | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
