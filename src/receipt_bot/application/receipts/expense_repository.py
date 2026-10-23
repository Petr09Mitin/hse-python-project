from abc import ABC, abstractmethod
from datetime import datetime

from receipt_bot.application.receipts.stored_receipt import StoredReceipt
from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.receipts.receipt import Receipt
from receipt_bot.domain.reports.report_period import ReportPeriod


class ExpenseRepository(ABC):
    """Потокобезопасные операции; временные сбои хранилища становятся StorageError."""

    @abstractmethod
    def find_by_source(self, owner_id: int, source_key: str) -> StoredReceipt | None:
        """Возвращает текущие категории и задачи, проверяя владельца."""

    @abstractmethod
    def save(self, receipt: Receipt, review_tasks: tuple[ReviewTask, ...]) -> StoredReceipt:
        """Сохраняет чек целиком; повтор владельца и исходного файла возвращает прежние данные."""

    @abstractmethod
    def get_review_task(self, owner_id: int, task_id: str) -> ReviewTask | None:
        """Чужая или отсутствующая задача возвращает None."""

    @abstractmethod
    def answer_review(self, owner_id: int, task_id: str, category: Category, answered_at: datetime) -> bool:
        """Атомарно меняет категорию и закрывает ожидающую задачу владельца.

        Возвращает False при закрытой/чужой задаче или недопустимом варианте. Никогда не переоткрывает задачу.
        """

    @abstractmethod
    def list_receipts(self, owner_id: int, period: ReportPeriod) -> tuple[Receipt, ...]:
        """Снимок чеков владельца по включительной дате покупки."""
