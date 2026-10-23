from abc import ABC, abstractmethod

from receipt_bot.application.messaging.incoming_message import IncomingMessage


class MessageReceiver(ABC):
    @abstractmethod
    def receive(self) -> IncomingMessage | None:
        """Получает следующий запрос в порядке поступления с ограниченным ожиданием.

        Не скачивает файлы, не выдаёт повторно выполняемые входы и завершённые входы,
        ожидающие подтверждения. None означает отсутствие нового запроса.
        """

    @abstractmethod
    def acknowledge(self, message: IncomingMessage) -> None:
        """Подтверждает исходные события после обработки и попыток доставки.

        Более ранние незавершённые события и ошибки хранилища не подтверждаются.
        """

    @abstractmethod
    def stop(self) -> None:
        """Останавливает приём и освобождает ресурсы."""
