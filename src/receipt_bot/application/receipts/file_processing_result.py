from dataclasses import dataclass

from receipt_bot.application.messaging.attachment_reference import AttachmentReference
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.receipts.receipt import Receipt


@dataclass(frozen=True)
class FileProcessingResult:
    """Результат обработки одного вложения."""

    reference: AttachmentReference
    status: str
    explanation: str
    receipt: Receipt | None = None
    review_tasks: tuple[ReviewTask, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_tasks", tuple(self.review_tasks))
