from abc import ABC, abstractmethod

from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.messaging.attachment_reference import AttachmentReference


class AttachmentDownloader(ABC):
    @abstractmethod
    def download(self, reference: AttachmentReference) -> Attachment:
        """Проверяет тип/размер при скачивании; отказ — FileProcessingError."""
