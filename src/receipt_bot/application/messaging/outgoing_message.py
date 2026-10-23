from dataclasses import dataclass

from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.domain.categories.review_task import ReviewTask


@dataclass(frozen=True)
class OutgoingMessage:
    """Адрес, текст и необязательный файл либо отдельный вопрос категории."""

    chat_id: int
    text: str
    export_file: Attachment | None = None
    review_task: ReviewTask | None = None
