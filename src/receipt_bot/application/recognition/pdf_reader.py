from abc import ABC, abstractmethod

from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.recognition.document_page import DocumentPage


class PDFReader(ABC):
    @abstractmethod
    def read(self, attachment: Attachment) -> tuple[DocumentPage, ...]:
        """Читает ограниченное число страниц, освобождая ресурсы до возврата."""
