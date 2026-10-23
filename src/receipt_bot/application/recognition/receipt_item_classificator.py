from abc import ABC, abstractmethod

from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData


class ReceiptItemClassificator(ABC):
    @abstractmethod
    def classify_item(self, item: StructuredItemData, categories: tuple[Category, ...]) -> Category | None:
        """Отдельный вызов для одной позиции без угадывания неизвестной категории."""
