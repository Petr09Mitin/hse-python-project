from abc import ABC, abstractmethod

from receipt_bot.domain.recognition.recognition_result import RecognitionResult


class OCRRunner(ABC):
    @abstractmethod
    def recognize(
        self, image: bytes, page_number: int = 1, width: float | None = None, height: float | None = None
    ) -> RecognitionResult:
        """Для PDF приводит координаты к указанным размерам страницы."""
