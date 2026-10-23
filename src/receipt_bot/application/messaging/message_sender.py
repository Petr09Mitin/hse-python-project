from abc import ABC, abstractmethod

from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage


class MessageSender(ABC):
    @abstractmethod
    def send(self, message: OutgoingMessage) -> DeliveryOutcome:
        """Возвращает конечный исход: максимум 3 попытки с конечным таймаутом каждой.

        Повторяет только временные отказы. Постоянный отказ завершает доставку сразу.
        Код ошибки безопасен для журнала и не содержит сырого ответа внешней системы.
        """
