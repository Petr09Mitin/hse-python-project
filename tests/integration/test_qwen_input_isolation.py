import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from telebot import TeleBot, apihelper

from receipt_bot.adapters.persistence.postgres_expense_repository import PostgresExpenseRepository
from receipt_bot.adapters.persistence.schema import prepare_schema
from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
from receipt_bot.adapters.telegram.telegram_message_sender import TelegramMessageSender
from receipt_bot.application.messaging.attachment_reference import AttachmentReference
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
from receipt_bot.application.receipts.message_processor import MessageProcessor
from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.bootstrap.application_runner import ApplicationRunner
from receipt_bot.domain.money import Money
from tests.helpers.http.http_server import scripted_server
from tests.helpers.messaging.scripted_receiver import ScriptedReceiver
from tests.helpers.recognition.recognition_ports import RecognitionPorts
from tests.integration.test_qwen_adapters import completion
from tests.integration.test_telegram_adapters import telegram_message


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_DSN"), reason="TEST_POSTGRES_DSN required")
@pytest.mark.parametrize("text", ["milk\x00bread", "\ud800"])
@pytest.mark.parametrize("field", ["item_name", "reason"])
def test_invalid_qwen_text_isolated_and_following_file_and_message_acknowledged(monkeypatch, field, text):
    dsn = os.environ["TEST_POSTGRES_DSN"]
    prepare_schema(dsn)
    data = {"purchase_date": "2026-10-22", "total": "1.00", "items": [{"item_name": "Хлеб", "item_price": "1.00"}]}
    decision = {"is_receipt": True, "reason": "Чек"}
    if field == "reason":
        values = [{"is_receipt": False, "reason": text}]
    else:
        values = [decision, {**data, "items": [{"item_name": text, "item_price": "1.00"}]}]
    values.extend((decision, data))
    with (
        scripted_server([(200, completion(value)) for value in values]) as (model, model_url),
        scripted_server([(200, {"ok": True, "result": telegram_message()})] * 2) as (telegram, telegram_url),
    ):
        monkeypatch.setattr(apihelper, "API_URL", telegram_url + "/bot{0}/{1}")
        client = QwenClient(model_url + "/v1", "qwen", timeout=2)
        repository = PostgresExpenseRepository(dsn)
        ports = RecognitionPorts()
        processor = MessageProcessor(
            repository,
            ports,
            ReceiptTextExtractor(ports, ports),
            QwenReceiptClassifier(client),
            QwenReceiptDataStructurer(client),
            ports,
            ReceiptSaver(repository),
        )
        owner = int(uuid4().int % 10**12) + 100
        bad = AttachmentReference(str(uuid4()), 0, "bad", "bad.jpg", "image/jpeg")
        good = AttachmentReference(str(uuid4()), 0, "good", "good.jpg", "image/jpeg")
        messages = (
            IncomingMessage(owner, owner, "receipt", "/receipt", (bad, good)),
            IncomingMessage(owner, owner, "following", "/unknown"),
        )
        receiver = ScriptedReceiver(messages)
        sender = TelegramMessageSender(TeleBot("123456:test-token", threaded=False), timeout=1)
        dispatcher = MessageDispatcher(processor, None, None, sender)
        runner = ApplicationRunner(receiver, dispatcher, workers=1, capacity=1, retry_delay=0.01, shutdown_timeout=1)
        with ThreadPoolExecutor(1) as worker:
            future = worker.submit(runner.run)
            try:
                assert receiver.idle.wait(3), "Следующее сообщение должно быть обработано"
                assert receiver.acknowledged == ["receipt", "following"]
            finally:
                runner.stop()
                client.close()
            future.result(timeout=3)
        assert repository.find_by_source(owner, bad.source_key) is None
        saved = repository.find_by_source(owner, good.source_key)
        assert saved is not None and saved.receipt.total == Money(10000)
        assert len(model.requests) == len(values)
        assert len(telegram.requests) == 2
        assert b"qwen_invalid_receipt_" in telegram.requests[0][0].encode()
