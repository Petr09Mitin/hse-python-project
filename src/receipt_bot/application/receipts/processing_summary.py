from dataclasses import dataclass

from receipt_bot.application.receipts.file_processing_result import FileProcessingResult
from receipt_bot.domain.money import Money


@dataclass(frozen=True)
class ProcessingSummary:
    """Итог сообщения без включения черновиков в подтверждённые расходы."""

    files: tuple[FileProcessingResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", tuple(self.files))

    @property
    def accounted_total(self) -> Money:
        total = Money(0)
        seen = set()
        for result in self.files:
            if result.status == "saved" and result.receipt.id not in seen:
                total += result.receipt.total
                seen.add(result.receipt.id)
        return total
