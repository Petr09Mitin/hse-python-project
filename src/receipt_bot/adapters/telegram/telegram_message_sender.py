import math
from io import BytesIO
from time import sleep

from telebot import TeleBot, types

from receipt_bot.adapters.telegram.telegram_error import TELEGRAM_ERRORS, error_details
from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome
from receipt_bot.application.messaging.message_sender import MessageSender
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage


class TelegramMessageSender(MessageSender):
    """Доставка с максимум тремя попытками и безопасным кодом отказа."""

    def __init__(self, bot: TeleBot, timeout: float = 15, retry_delay: float = 0.2):
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(retry_delay) or not 0 <= retry_delay <= 2:
            raise ValueError("Некорректные таймауты Telegram")
        self.bot = bot
        self.timeout = timeout
        self.retry_delay = retry_delay

    def send(self, message: OutgoingMessage) -> DeliveryOutcome:
        keyboard = None
        if message.review_task is not None:
            keyboard = types.InlineKeyboardMarkup()
            for category in message.review_task.options:
                callback = f"category:{message.review_task.id}:{category.code}"
                if len(callback.encode()) > 64:
                    return DeliveryOutcome("permanent_failure", "telegram_callback_too_long")
                keyboard.add(types.InlineKeyboardButton(category.name, callback_data=callback))
        for attempt in range(1, 4):
            try:
                for start in range(0, len(message.text), 4000):
                    self.bot.send_message(
                        message.chat_id,
                        message.text[start : start + 4000],
                        reply_markup=keyboard,
                        timeout=self.timeout,
                        parse_mode=None,
                    )
                if message.export_file is not None:
                    with BytesIO(message.export_file.content) as source:
                        self.bot.send_document(
                            message.chat_id,
                            types.InputFile(source, file_name=message.export_file.file_name),
                            timeout=self.timeout,
                        )
            except TELEGRAM_ERRORS as error:
                temporary, code, delay = error_details(error)
                if not temporary:
                    return DeliveryOutcome("permanent_failure", code, attempt)
                if attempt == 3:
                    return DeliveryOutcome("exhausted", code, attempt)
                sleep(max(delay, self.retry_delay))
            else:
                return DeliveryOutcome("delivered", attempts=attempt)
