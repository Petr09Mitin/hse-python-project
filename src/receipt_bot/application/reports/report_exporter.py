from abc import ABC, abstractmethod

from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.domain.reports.expense_report import ExpenseReport


class ReportExporter(ABC):
    @abstractmethod
    def export(self, report: ExpenseReport) -> Attachment:
        """Экспортирует готовые точные суммы, освобождая ресурсы до возврата."""
