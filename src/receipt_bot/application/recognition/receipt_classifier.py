from abc import ABC, abstractmethod

from receipt_bot.domain.recognition.receipt_decision import ReceiptDecision
from receipt_bot.domain.recognition.recognition_result import RecognitionResult


class ReceiptClassifier(ABC):
    @abstractmethod
    def classify(self, recognition: RecognitionResult) -> ReceiptDecision:
        """Отдельный вызов определения чека."""
