import json
from urllib.parse import parse_qs, urlsplit

import pytest
from telebot import TeleBot, apihelper

from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.messaging.attachment_reference import AttachmentReference
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.categories.review_task import ReviewTask
from tests.helpers.http.http_server import scripted_server


def telegram_message(text="ok"):
    return {"message_id": 1, "date": 1, "chat": {"id": 10, "type": "private"}, "text": text}


@pytest.fixture
def sdk(monkeypatch):
    apihelper.RETRY_ON_ERROR = False
    apihelper.CONNECT_TIMEOUT = 1
    apihelper.READ_TIMEOUT = 1
    monkeypatch.setattr(apihelper, "LONG_POLLING_TIMEOUT", 1)
    return TeleBot("123456:test-token", threaded=False, skip_pending=False)


def test_sender_uses_sdk_keyboard_document_and_final_safe_outcomes(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_sender import TelegramMessageSender

    with scripted_server([(200, {"ok": True, "result": telegram_message()})] * 3) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        sender = TelegramMessageSender(sdk, timeout=1, retry_delay=0)
        task = ReviewTask("task", 1, "item", DEFAULT_CATEGORIES)
        assert sender.send(OutgoingMessage(10, "Категория?", review_task=task)).status == "delivered"
        assert (
            sender.send(
                OutgoingMessage(10, "Отчёт", export_file=Attachment("report.xlsx", "application/octet-stream", b"file"))
            ).status
            == "delivered"
        )
        keyboard = parse_qs(urlsplit(server.requests[0][0]).query)["reply_markup"][0]
        assert json.loads(keyboard)["inline_keyboard"][0][0]["callback_data"] == "category:task:food"
        assert urlsplit(server.requests[-1][0]).path.endswith("/sendDocument")
        assert b"report.xlsx" in server.requests[-1][1]
    with scripted_server([(200, {"ok": False, "error_code": 403, "description": "SECRET raw bot URL"})]) as (
        server,
        url,
    ):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        result = sender.send(OutgoingMessage(10, "Ответ"))
        assert result.status == "permanent_failure" and result.attempts == 1
        assert result.error_code == "telegram_403"
    with scripted_server(
        [(200, {"ok": False, "error_code": 429, "description": "limited", "parameters": {"retry_after": 0}})] * 3
    ) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        result = sender.send(OutgoingMessage(10, "Ответ"))
        assert result.status == "exhausted" and result.attempts == 3
        assert len(server.requests) == 3


def update(identifier, text="", group=None, callback=None):
    message = {**telegram_message(text), "from": {"id": 1, "is_bot": False, "first_name": "T"}}
    if group is not None:
        message["media_group_id"] = group
        message["caption"] = text
        message.pop("text")
        message["photo"] = [
            {
                "file_id": f"file-{identifier}",
                "file_unique_id": f"u-{identifier}",
                "width": 10,
                "height": 10,
                "file_size": 10,
            }
        ]
    if callback:
        return {
            "update_id": identifier,
            "callback_query": {
                "id": "cb",
                "from": message["from"],
                "chat_instance": "x",
                "message": message,
                "data": callback,
            },
        }
    return {"update_id": identifier, "message": message}


def test_receiver_deduplicates_running_and_done_events_until_prefix_ack(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    incoming = [update(10, "/report"), update(14, "/receipt")]
    responses = [
        (200, {"ok": True, "result": incoming}),
        (200, {"ok": True, "result": incoming}),
        (200, {"ok": True, "result": []}),
    ]
    with scripted_server(responses) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, poll_timeout=1, request_timeout=1)
        first, second = receiver.receive(), receiver.receive()
        assert first.event_id == "10" and second.event_id == "14"
        receiver.acknowledge(second)
        assert receiver.receive() is None
        receiver.acknowledge(first)
        assert receiver.receive() is None
        parameters = parse_qs(urlsplit(server.requests[-1][0]).query)
        assert parameters["offset"] == ["15"]
        assert json.loads(parameters["allowed_updates"][0]) == ["message", "callback_query"]
        receiver.stop()
        assert receiver.receive() is None


def test_receiver_aggregates_album_and_explains_late_file(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    now = [0]
    responses = [
        (200, {"ok": True, "result": [update(20, "/receipt", "album"), update(21, "", "album")]}),
        (200, {"ok": True, "result": [update(22, "", "album")]}),
    ]
    with scripted_server(responses) as (_, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, clock=lambda: now[0], poll_timeout=1, request_timeout=1)
        assert receiver.receive() is None
        now[0] = 2
        album = receiver.receive()
        assert album.command == "/receipt"
        assert album.acknowledgement_ids == ("20", "21")
        assert [reference.source_event_id for reference in album.attachments] == ["20", "21"]
        receiver.acknowledge(album)
        late = receiver.receive()
        assert late.rejection_reason and "/receipt" in late.rejection_reason
        receiver.acknowledge(late)


def test_receiver_normalizes_callback_and_acknowledges_telegram_query(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    responses = [
        (200, {"ok": True, "result": [update(40, callback="category:task:food")]}),
        (200, {"ok": True, "result": True}),
    ]
    with scripted_server(responses) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, poll_timeout=1, request_timeout=1)
        message = receiver.receive()
        assert message.review_choice.task_id == "task"
        assert message.review_choice.category_code == "food"
        assert server.requests[-1][0].split("?")[0].endswith("answerCallbackQuery")


def test_downloader_checks_metadata_and_stream_limit_without_sdk_download(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_attachment_downloader import TelegramAttachmentDownloader

    file_info = {
        "ok": True,
        "result": {"file_id": "file", "file_unique_id": "u", "file_size": 2, "file_path": "photo.jpg"},
    }
    with scripted_server([(200, file_info), (200, b"\xff\xd8\xffimage")]) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        monkeypatch.setattr(apihelper, "FILE_URL", url + "/file/bot{0}/{1}")
        downloader = TelegramAttachmentDownloader(sdk, max_bytes=10, timeout=1)
        attachment = downloader.download(AttachmentReference("50", 0, "file", "photo.jpg", "image/jpeg"))
        assert attachment.content == b"\xff\xd8\xffimage"
        assert len(server.requests) == 2
    with scripted_server([(200, file_info), (200, b"\xff\xd8\xff" + b"x" * 30)]) as (_, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        monkeypatch.setattr(apihelper, "FILE_URL", url + "/file/bot{0}/{1}")
        with pytest.raises(FileProcessingError, match="attachment_too_large"):
            downloader.download(AttachmentReference("51", 0, "file", "photo.jpg", "image/jpeg"))
    with pytest.raises(FileProcessingError, match="attachment_too_large"):
        downloader.download(AttachmentReference("52", 0, "file", "photo.jpg", "image/jpeg", 11))


def test_receiver_buffer_stays_bounded_when_earlier_work_is_running(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    with scripted_server([(200, {"ok": True, "result": [update(1, "/receipt"), update(3, "/report")]})]) as (
        server,
        url,
    ):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, max_buffered_updates=2, poll_timeout=1, request_timeout=1)
        first, second = receiver.receive(), receiver.receive()
        receiver.acknowledge(second)
        assert receiver.receive() is None
        assert len(server.requests) == 1
        receiver.acknowledge(first)


def test_album_total_deadline_closes_even_with_continuing_items(sdk, monkeypatch):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    now = [0]
    incoming = [update(60, "/receipt", "g")]
    responses = [(200, {"ok": True, "result": incoming.copy()})]
    for identifier in (61, 62, 63):
        incoming.append(update(identifier, "", "g"))
        responses.append((200, {"ok": True, "result": incoming.copy()}))
    with scripted_server(responses) as (_, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, poll_timeout=1, request_timeout=1, clock=lambda: now[0])
        for instant in (0, 1.5, 3, 4.5):
            now[0] = instant
            assert receiver.receive() is None
        now[0] = 5
        album = receiver.receive()
        assert album.acknowledgement_ids == ("60", "61", "62", "63")
        assert album.attachments[0].source_key == "2:60:0"


@pytest.mark.parametrize(
    "malformed", ["blank_callback_task", "nul_callback_task", "surrogate_callback_category", "blank_document_name"]
)
def test_invalid_telegram_fields_are_rejected_without_blocking_ack_prefix(sdk, monkeypatch, malformed):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    if malformed != "blank_document_name":
        callbacks = {
            "blank_callback_task": "category: :food",
            "nul_callback_task": "category:bad\x00task:food",
            "surrogate_callback_category": "category:task:\ud800",
        }
        invalid = update(80, callback=callbacks[malformed])
        callback_reply = [(200, {"ok": True, "result": True})]
    else:
        invalid = update(80, "/receipt")
        invalid["message"]["document"] = {
            "file_id": "file",
            "file_unique_id": "unique",
            "file_name": "   ",
            "mime_type": "application/pdf",
            "file_size": 10,
        }
        callback_reply = []
    responses = [(200, json.dumps({"ok": True, "result": [invalid, update(82, "/report")]}).encode())]
    responses.extend(callback_reply)
    responses.append((200, {"ok": True, "result": []}))
    with scripted_server(responses) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, poll_timeout=1, request_timeout=1)
        rejection = receiver.receive()
        assert rejection.event_id == "80"
        assert rejection.rejection_reason
        following = receiver.receive()
        assert following.command == "/report"
        receiver.acknowledge(following)
        receiver.acknowledge(rejection)
        assert receiver.receive() is None
        assert parse_qs(urlsplit(server.requests[-1][0]).query)["offset"] == ["83"]


@pytest.mark.parametrize(
    "earlier_arrivals,poll_started,poll_finished,expected_album_ids",
    [
        ((), 1.9, 2.1, ("90",)),
        ((1.5, 3, 4.5), 4.9, 5.1, ("90", "91", "92", "93")),
    ],
)
def test_album_rejects_item_when_deadline_passes_during_poll(
    sdk, monkeypatch, earlier_arrivals, poll_started, poll_finished, expected_album_ids
):
    from receipt_bot.adapters.telegram.telegram_message_receiver import TelegramMessageReceiver

    now = [0]
    incoming = [update(90, "/receipt", "deadline")]
    responses = [(200, {"ok": True, "result": incoming.copy()})]
    for identifier, _ in enumerate(earlier_arrivals, start=91):
        incoming.append(update(identifier, "", "deadline"))
        responses.append((200, {"ok": True, "result": incoming.copy()}))
    incoming.append(update(99, "", "deadline"))
    responses.extend([(200, {"ok": True, "result": incoming}), (200, {"ok": True, "result": []})])
    original_get_updates = sdk.get_updates

    def finish_poll_after_deadline(**parameters):
        result = original_get_updates(**parameters)
        if now[0] == poll_started:
            now[0] = poll_finished
        return result

    monkeypatch.setattr(sdk, "get_updates", finish_poll_after_deadline)
    with scripted_server(responses) as (server, url):
        monkeypatch.setattr(apihelper, "API_URL", url + "/bot{0}/{1}")
        receiver = TelegramMessageReceiver(sdk, clock=lambda: now[0], poll_timeout=1, request_timeout=1)
        assert receiver.receive() is None
        for instant in earlier_arrivals:
            now[0] = instant
            assert receiver.receive() is None
        now[0] = poll_started
        album = receiver.receive()
        assert album is not None
        assert album.acknowledgement_ids == expected_album_ids
        late = receiver.receive()
        assert late.event_id == "99" and late.rejection_reason
        assert "/receipt" in late.rejection_reason
        receiver.acknowledge(late)
        receiver.acknowledge(album)
        assert receiver.receive() is None
        assert parse_qs(urlsplit(server.requests[-1][0]).query)["offset"] == ["100"]
