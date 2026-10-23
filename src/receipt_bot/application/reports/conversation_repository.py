from abc import ABC, abstractmethod
from collections.abc import Callable

from receipt_bot.application.reports.report_conversation import ReportConversation
from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution


class ConversationRepository(ABC):
    @abstractmethod
    def transition(
        self,
        owner_id: int,
        chat_id: int,
        event_id: str,
        change: Callable[[ReportConversation | None], tuple[ReportConversation | None, ReportPeriodResolution]],
    ) -> ReportPeriodResolution:
        """В одной транзакции меняет состояние диалога и запоминает ответ.

        Повтор события возвращает прежний результат без повторного изменения.
        Ответ сохраняется и после завершения диалога. Обработчик не обращается к внешним системам.
        При ошибке вся операция откатывается; временные сбои становятся StorageError.
        Контракт действует между потоками и процессами.
        """
