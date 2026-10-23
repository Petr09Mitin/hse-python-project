import re
from datetime import date, datetime

from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.reports.conversation_repository import ConversationRepository
from receipt_bot.application.reports.report_conversation import ReportConversation
from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution
from receipt_bot.domain.reports.report_period import ReportPeriod


class ReportPeriodResolver:
    """Определяет период отчёта по команде или ответам пользователя."""

    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    def resolve(self, message: IncomingMessage) -> ReportPeriodResolution:
        if message.review_choice is not None or message.command not in (None, "/report", "/cancel"):
            return ReportPeriodResolution("ignored")

        def change(state: ReportConversation | None) -> tuple[ReportConversation | None, ReportPeriodResolution]:
            if state is not None and (state.owner_id != message.owner_id or state.chat_id != message.chat_id):
                raise StorageError("conversation_owner_mismatch")
            if message.command == "/cancel":
                return None, ReportPeriodResolution("cancelled", "Запрос периода отменён.")
            if message.command == "/report":
                return self._command(message)
            return self._answer(message, state)

        return self.repository.transition(message.owner_id, message.chat_id, message.event_id, change)

    def _command(self, message: IncomingMessage) -> tuple[ReportConversation | None, ReportPeriodResolution]:
        words = message.text.split()
        arguments = words
        for index, word in enumerate(words):
            if word.split("@", 1)[0] == "/report":
                arguments = words[index + 1 :]
                break
        if not arguments:
            return ReportConversation(message.owner_id, message.chat_id, "start"), ReportPeriodResolution(
                "question", "Введите начало периода в формате ДД.ММ.ГГГГ."
            )
        if len(arguments) != 2:
            return None, ReportPeriodResolution("error", "Используйте /report ДД.ММ.ГГГГ ДД.ММ.ГГГГ.")
        try:
            period = ReportPeriod(self._date(arguments[0]), self._date(arguments[1]))
        except ValueError:
            return None, ReportPeriodResolution(
                "error", "Проверьте календарные даты ДД.ММ.ГГГГ: начало должно быть не позже конца."
            )
        return None, ReportPeriodResolution("ready", period=period)

    def _answer(
        self, message: IncomingMessage, state: ReportConversation | None
    ) -> tuple[ReportConversation | None, ReportPeriodResolution]:
        if state is None:
            return None, ReportPeriodResolution("ignored")
        try:
            answer = self._date(message.text.strip())
        except ValueError:
            boundary = "начало" if state.stage == "start" else "конец"
            return state, ReportPeriodResolution("error", f"Введите корректное {boundary} периода: ДД.ММ.ГГГГ.")
        if state.stage == "start":
            return ReportConversation(message.owner_id, message.chat_id, "end", answer), ReportPeriodResolution(
                "question", "Введите конец периода в формате ДД.ММ.ГГГГ."
            )
        if answer < state.start_date:
            return state, ReportPeriodResolution(
                "error", "Конец периода не может быть раньше начала. Введите конец снова."
            )
        return None, ReportPeriodResolution("ready", period=ReportPeriod(state.start_date, answer))

    def _date(self, text: str) -> date:
        if re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", text) is None:
            raise ValueError("Ожидается ДД.ММ.ГГГГ")
        return datetime.strptime(text, "%d.%m.%Y").date()
