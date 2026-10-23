import logging
from collections import OrderedDict, deque
from dataclasses import replace
from threading import Event, Lock
from time import monotonic

from telebot import TeleBot

from receipt_bot.adapters.telegram.telegram_album import TelegramAlbum
from receipt_bot.adapters.telegram.telegram_error import TELEGRAM_ERRORS
from receipt_bot.application.categories.review_choice import ReviewChoice
from receipt_bot.application.messaging.attachment_reference import AttachmentReference
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.messaging.message_receiver import MessageReceiver

logger = logging.getLogger(__name__)


class TelegramMessageReceiver(MessageReceiver):
    """Получает сообщения Telegram и подтверждает завершённые запросы."""

    def __init__(
        self,
        bot: TeleBot,
        max_buffered_updates: int = 16,
        poll_timeout: int = 1,
        request_timeout: int = 10,
        album_idle: float = 2,
        album_total: float = 5,
        clock=monotonic,
    ):
        if not 1 <= max_buffered_updates <= 100 or poll_timeout < 1 or request_timeout < 1:
            raise ValueError("Некорректные лимиты polling")
        if not 0 < album_idle <= album_total <= 5:
            raise ValueError("Некорректный срок сбора альбома")
        self.bot = bot
        self.max_buffered_updates = max_buffered_updates
        self.poll_timeout = poll_timeout
        self.request_timeout = request_timeout
        self.album_idle = album_idle
        self.album_total = album_total
        self.clock = clock
        self.offset = None
        self.events = OrderedDict()
        self.ready = deque()
        self.albums = {}
        self.closed_albums = OrderedDict()
        self.lock = Lock()
        self.stopped = Event()

    def receive(self) -> IncomingMessage | None:
        if self.stopped.is_set():
            return None
        with self.lock:
            self._flush_albums()
            if self.ready:
                return self._take_ready()
            full = len(self.events) >= self.max_buffered_updates
            offset = self.offset
        if full:
            self.stopped.wait(0.05)
            return None
        try:
            updates = self.bot.get_updates(
                offset=offset,
                limit=self.max_buffered_updates,
                timeout=self.request_timeout,
                long_polling_timeout=self.poll_timeout,
                allowed_updates=["message", "callback_query"],
            )
        except TELEGRAM_ERRORS as error:
            raise RuntimeError("telegram_receive_failed") from error
        callbacks = []
        with self.lock:
            self._flush_albums()
            for update in sorted(updates, key=lambda update: update.update_id):
                identifier = update.update_id
                if identifier in self.events or (self.offset is not None and identifier < self.offset):
                    continue
                if len(self.events) >= self.max_buffered_updates:
                    break
                self.events[identifier] = "pending"
                try:
                    self._accept(update)
                except (TypeError, ValueError):
                    self._reject_invalid(update)
                if update.callback_query is not None:
                    callbacks.append(update.callback_query.id)
            self._flush_albums()
            self._advance_offset()
            message = self._take_ready() if self.ready else None
        for callback_id in callbacks:
            try:
                self.bot.answer_callback_query(callback_id)
            except TELEGRAM_ERRORS:
                logger.warning("telegram_callback_ack_failed")
        if message is None:
            self.stopped.wait(0.05)
        return message

    def _take_ready(self) -> IncomingMessage:
        message = self.ready.popleft()
        for identifier in message.acknowledgement_ids:
            self.events[int(identifier)] = "running"
        return message

    def _reject_invalid(self, update) -> None:
        callback = update.callback_query
        raw = callback.message if callback is not None else update.message
        author = callback.from_user if callback is not None else raw.from_user
        try:
            self._check_address(author.id, raw.chat.id)
            message = IncomingMessage(
                author.id,
                raw.chat.id,
                str(update.update_id),
                rejection_reason="Некорректные данные сообщения. Отправьте запрос или файл снова.",
            )
        except (TypeError, ValueError):
            self.events[update.update_id] = "done"
            logger.warning("telegram_invalid_message_address")
        else:
            self.ready.append(message)

    def _accept(self, update) -> None:
        event_id = str(update.update_id)
        callback = update.callback_query
        raw = callback.message if callback is not None else update.message
        author = callback.from_user if callback is not None else (None if raw is None else raw.from_user)
        if raw is None or author is None or author.is_bot:
            self.events[update.update_id] = "done"
            return
        self._check_address(author.id, raw.chat.id)
        text = raw.text or raw.caption or ""
        if not isinstance(text, str):
            raise TypeError("Текст сообщения должен быть строкой")
        choice = None
        rejection = None
        if callback is not None:
            data = callback.data or ""
            if not isinstance(data, str):
                raise TypeError("Данные кнопки должны быть строкой")
            if "\x00" in data:
                raise ValueError("Кнопка содержит NUL")
            data.encode("utf-8")
            parts = data.split(":")
            if len(parts) == 3 and parts[0] == "category" and parts[1].strip() and parts[2].strip():
                choice = ReviewChoice(parts[1], parts[2])
            else:
                rejection = "Некорректная кнопка. Повторите запрос."
        attachments = []
        if raw.document is not None:
            document = raw.document
            attachments.append(
                AttachmentReference(
                    event_id,
                    0,
                    document.file_id,
                    document.file_name or "document",
                    document.mime_type or "application/octet-stream",
                    document.file_size,
                )
            )
        elif raw.photo:
            photo = max(raw.photo, key=lambda photo: photo.width * photo.height)
            attachments.append(
                AttachmentReference(event_id, 0, photo.file_id, f"photo_{event_id}.jpg", "image/jpeg", photo.file_size)
            )
        for reference in attachments:
            for value in (reference.source_token, reference.file_name, reference.media_type):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Не заданы сведения о файле")
            if reference.size_bytes is not None and (type(reference.size_bytes) is not int or reference.size_bytes < 0):
                raise ValueError("Некорректный размер файла")
        message = IncomingMessage(
            author.id,
            raw.chat.id,
            event_id,
            text,
            tuple(attachments),
            choice,
            rejection_reason=rejection,
        )
        group_id = raw.media_group_id if callback is None else None
        if group_id is None:
            self.ready.append(message)
            return
        key = (raw.chat.id, group_id)
        if key in self.closed_albums:
            self.ready.append(
                replace(message, rejection_reason="Альбом уже завершён. Отправьте поздний файл снова с /receipt.")
            )
            return
        now = self.clock()
        album = self.albums.setdefault(key, TelegramAlbum(now, now))
        if album.messages and album.messages[0].owner_id != message.owner_id:
            self.ready.append(replace(message, rejection_reason="Отправьте файл отдельно с /receipt."))
            return
        album.messages.append(message)
        album.updated_at = now
        if len(self.events) >= self.max_buffered_updates:
            self._close_album(key)

    @staticmethod
    def _check_address(owner_id: int, chat_id: int) -> None:
        if type(owner_id) is not int or owner_id <= 0 or type(chat_id) is not int:
            raise ValueError("Некорректный адрес сообщения")

    def _flush_albums(self) -> None:
        now = self.clock()
        for key, album in list(self.albums.items()):
            if now - album.updated_at >= self.album_idle or now - album.started_at >= self.album_total:
                self._close_album(key)

    def _close_album(self, key: tuple) -> None:
        album = self.albums.pop(key)
        first = album.messages[0]
        text = "\n".join(message.text for message in album.messages if message.text)
        attachments = tuple(reference for message in album.messages for reference in message.attachments)
        identifiers = tuple(message.event_id for message in album.messages)
        self.ready.append(
            IncomingMessage(
                first.owner_id, first.chat_id, first.event_id, text, attachments, acknowledgement_ids=identifiers
            )
        )
        self.closed_albums[key] = True
        # shortcut: помним 1024 media_group_id; расширить хранилище, если нужны более старые поздние элементы.
        if len(self.closed_albums) > 1024:
            self.closed_albums.popitem(last=False)

    def acknowledge(self, message: IncomingMessage) -> None:
        with self.lock:
            for identifier in message.acknowledgement_ids:
                if int(identifier) not in self.events:
                    raise ValueError("Событие не принято receiver")
            for identifier in message.acknowledgement_ids:
                self.events[int(identifier)] = "done"
            self._advance_offset()

    def _advance_offset(self) -> None:
        while self.events:
            identifier = next(iter(self.events))
            if self.events[identifier] != "done":
                break
            self.events.pop(identifier)
            self.offset = identifier + 1

    def stop(self) -> None:
        self.stopped.set()
