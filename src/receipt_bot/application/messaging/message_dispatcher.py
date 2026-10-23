from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.messaging.message_sender import MessageSender
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage
from receipt_bot.application.messaging.prepared_message import PreparedMessage
from receipt_bot.application.receipts.message_processor import MessageProcessor
from receipt_bot.application.receipts.processing_summary import ProcessingSummary
from receipt_bot.application.reports.report_processor import ReportProcessor


class MessageDispatcher:
    """Выбирает обработчик запроса и отправляет ответ."""

    def __init__(
        self,
        receipts: MessageProcessor,
        reviews: CategoryReviewProcessor,
        reports: ReportProcessor,
        sender: MessageSender,
    ):
        self.receipts = receipts
        self.reviews = reviews
        self.reports = reports
        self.sender = sender

    def prepare(self, message: IncomingMessage) -> PreparedMessage:
        """Запоминает маршрут запроса и переход диалога дат."""
        if message.rejection_reason is not None:
            return PreparedMessage(message, "help")
        if message.review_choice is not None:
            return PreparedMessage(message, "review")
        if message.command == "/receipt":
            return PreparedMessage(message, "receipt")
        if message.command in (None, "/report", "/cancel"):
            resolution = self.reports.prepare(message)
            if resolution.kind != "ignored":
                return PreparedMessage(message, "report", resolution)
        return PreparedMessage(message, "help")

    def dispatch(self, prepared: PreparedMessage) -> tuple[DeliveryOutcome, ...]:
        """Обрабатывает запрос и возвращает результаты доставки."""
        message = prepared.message
        if prepared.route == "receipt":
            outgoing = self._receipt_messages(message)
        elif prepared.route == "review":
            text = self.reviews.process(message.owner_id, message.review_choice)
            outgoing = [OutgoingMessage(message.chat_id, text)]
        elif prepared.route == "report":
            outgoing = [self.reports.process(message, prepared.resolution)]
        else:
            outgoing = [
                OutgoingMessage(
                    message.chat_id,
                    message.rejection_reason or "Отправьте фото или PDF с /receipt. Для отчёта: /report.",
                )
            ]
        outcomes = []
        for response in outgoing:
            outcome = self.sender.send(response)
            outcomes.append(outcome)
        return tuple(outcomes)

    def _receipt_messages(self, message: IncomingMessage) -> list[OutgoingMessage]:
        if not message.attachments:
            return [OutgoingMessage(message.chat_id, "Прикрепите фото или PDF к сообщению с /receipt.")]
        summary = self.receipts.process(message)
        outgoing = [OutgoingMessage(message.chat_id, self._summary_text(summary))]
        asked = set()
        for result in summary.files:
            if result.receipt is None:
                continue
            for task in result.review_tasks:
                if task.id in asked:
                    continue
                item = next(item for item in result.receipt.items if item.id == task.item_id)
                text = f"Выберите категорию: {item.item_name or 'непрочитанная позиция'}."
                outgoing.append(OutgoingMessage(message.chat_id, text, review_task=task))
                asked.add(task.id)
        return outgoing

    def _summary_text(self, summary: ProcessingSummary) -> str:
        lines = []
        labels = {
            "saved": "сохранён",
            "draft": "черновик, исключён из расходов",
            "skipped": "пропущен",
            "error": "ошибка",
        }
        for result in summary.files:
            lines.append(f"{result.reference.file_name}: {labels[result.status]}. {result.explanation}")
        rubles, fraction = divmod(summary.accounted_total.units, 10000)
        lines.append(f"Учтённый итог: {rubles}.{fraction:04d} ₽.")
        return "\n".join(lines)
