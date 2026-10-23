from abc import ABC, abstractmethod

from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData


class ReceiptDataStructurer(ABC):
    @abstractmethod
    def structure(self, recognition: RecognitionResult) -> StructuredReceiptData:
        """Отдельный вызов извлечения; JSON/схема проверяются адаптером."""
