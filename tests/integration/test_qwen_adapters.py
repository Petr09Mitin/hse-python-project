import json
import os
from datetime import date

import pytest

from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData
from receipt_bot.domain.recognition.text_line import TextLine
from tests.helpers.http.http_server import scripted_server


def completion(value, finish="stop"):
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 1,
        "model": "qwen",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(value)},
                "finish_reason": finish,
            }
        ],
    }


def recognition():
    return RecognitionResult((TextLine(1, 0, "МОЛОКО 12.3456 ИТОГ 12.3456 22.10.2026", (0, 0, 100, 10)),))


def test_three_qwen_stages_send_separate_strict_schemas_and_exact_money():
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
    from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator

    responses = [
        (200, completion({"is_receipt": True, "reason": "Чек"})),
        (
            200,
            completion(
                {
                    "purchase_date": "2026-10-22",
                    "total": "12.3456",
                    "items": [{"item_name": "Молоко", "item_price": "12.3456"}],
                }
            ),
        ),
        (200, completion({"category_code": "food", "needs_review": False})),
        (200, completion({"category_code": None, "needs_review": True})),
    ]
    with scripted_server(responses) as (server, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            assert QwenReceiptClassifier(client).classify(recognition()).is_receipt
            data = QwenReceiptDataStructurer(client).structure(recognition())
            assert data.total == Money(123456)
            classifier = QwenReceiptItemClassificator(client)
            assert classifier.classify_item(data.items[0], DEFAULT_CATEGORIES) == DEFAULT_CATEGORIES[0]
            assert classifier.classify_item(StructuredItemData(None, None), DEFAULT_CATEGORIES) is None
            payloads = [json.loads(request[1]) for request in server.requests]
            assert len(payloads) == 4
            for payload in payloads:
                assert payload["stream"] is False
                assert payload["chat_template_kwargs"]["enable_thinking"] is False
                assert payload["response_format"]["json_schema"]["strict"] is True
                assert payload["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        finally:
            client.close()


@pytest.mark.parametrize(
    "value,finish",
    [
        ({"is_receipt": "yes", "reason": "чек"}, "stop"),
        ({"is_receipt": True, "reason": "чек", "other": 1}, "stop"),
        ({"is_receipt": True, "reason": "чек"}, "length"),
    ],
)
def test_invalid_model_output_never_becomes_a_decision(value, finish):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier

    with scripted_server([(200, completion(value, finish))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            with pytest.raises(FileProcessingError):
                QwenReceiptClassifier(client).classify(recognition())
        finally:
            client.close()


@pytest.mark.parametrize(
    "value",
    [
        {"category_code": "unknown", "needs_review": False},
        {"category_code": None, "needs_review": False},
        {"category_code": "food", "needs_review": True},
        {"category_code": "food", "needs_review": "false"},
    ],
)
def test_qwen_rejects_unknown_or_inconsistent_category(value):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator

    with scripted_server([(200, completion(value))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            with pytest.raises(FileProcessingError, match="qwen_invalid_item_category"):
                QwenReceiptItemClassificator(client).classify_item(
                    StructuredItemData("Хлеб", Money(1)), DEFAULT_CATEGORIES
                )
        finally:
            client.close()


@pytest.mark.parametrize("price", [1.25, "0.00001", "NaN", "-1", "1e3"])
def test_qwen_rejects_inexact_or_invalid_money(price):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    with scripted_server([(200, completion({"purchase_date": None, "total": price, "items": []}))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            with pytest.raises(FileProcessingError):
                QwenReceiptDataStructurer(client).structure(recognition())
        finally:
            client.close()


def test_temporary_qwen_failure_is_bounded_and_permanent_failure_is_not_retried():
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier

    with scripted_server([(503, {"error": {"message": "temporary"}})] * 2) as (server, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2, retry_delay=0)
        try:
            with pytest.raises(FileProcessingError, match="qwen_unavailable"):
                QwenReceiptClassifier(client).classify(recognition())
            assert len(server.requests) == 2
        finally:
            client.close()
    with scripted_server([(400, {"error": {"message": "invalid"}})]) as (server, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2, retry_delay=0)
        try:
            with pytest.raises(FileProcessingError):
                QwenReceiptClassifier(client).classify(recognition())
            assert len(server.requests) == 1
        finally:
            client.close()


@pytest.mark.parametrize("retry_after", ["7", "invalid", "NaN"])
def test_qwen_rate_limit_blocks_all_calls_until_provider_cooldown_expires(monkeypatch, retry_after):
    from receipt_bot.adapters.recognition import qwen_client
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier

    now = [100.0]
    monkeypatch.setattr(qwen_client, "monotonic", lambda: now[0], raising=False)
    responses = [
        (429, {"error": {"message": "rate limited"}}, {"Retry-After": retry_after}),
        (200, completion({"is_receipt": True, "reason": "Чек"})),
    ]
    with scripted_server(responses) as (server, url):
        client = qwen_client.QwenClient(url + "/v1", "qwen", timeout=2, retry_delay=0)
        try:
            classifier = QwenReceiptClassifier(client)
            with pytest.raises(FileProcessingError, match="qwen_unavailable"):
                classifier.classify(recognition())
            assert len(server.requests) == 1
            now[0] += 6
            with pytest.raises(FileProcessingError, match="qwen_unavailable"):
                classifier.classify(recognition())
            assert len(server.requests) == 1
            now[0] += 1 if retry_after == "7" else 54
            assert classifier.classify(recognition()).is_receipt
            assert len(server.requests) == 2
        finally:
            client.close()


@pytest.mark.skipif(not os.getenv("TEST_QWEN_URL"), reason="TEST_QWEN_URL required for actual model")
def test_live_qwen_classifies_and_extracts_receipt():
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
    from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator

    client = QwenClient(os.environ["TEST_QWEN_URL"], "qwen3-1.7b", timeout=120)
    text = RecognitionResult(
        (TextLine(1, 0, "КАССОВЫЙ ЧЕК\n22.10.2026\nМолоко 100.00\nИТОГ 100.00", (0, 0, 100, 100)),)
    )
    try:
        assert QwenReceiptClassifier(client).classify(text).is_receipt
        data = QwenReceiptDataStructurer(client).structure(text)
        assert data.total == Money(1000000)
        assert len(data.items) == 1
        result = QwenReceiptItemClassificator(client).classify_item(data.items[0], DEFAULT_CATEGORIES)
        assert result in (DEFAULT_CATEGORIES[0], None)
    finally:
        client.close()


@pytest.mark.parametrize("body", [b"not JSON", b"{", b"\xff"])
def test_sdk_response_decode_error_is_a_file_error_and_next_file_still_works(body):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier

    responses = [(200, body), (200, completion({"is_receipt": True, "reason": "Чек"}))]
    with scripted_server(responses) as (server, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            classifier = QwenReceiptClassifier(client)
            with pytest.raises(FileProcessingError, match="qwen_invalid_response"):
                classifier.classify(recognition())
            assert classifier.classify(recognition()).is_receipt
            assert len(server.requests) == 2
        finally:
            client.close()


@pytest.mark.parametrize("field", ["total", "item_price"])
def test_qwen_rejects_storage_overflow_and_next_file_accepts_maximum_amount(field):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    overflow = "1" + "0" * 34
    maximum = "9999999999999999999999999999999999.9999"
    invalid = {
        "purchase_date": "2026-10-22",
        "total": overflow if field == "total" else "12.3456",
        "items": [{"item_name": "Молоко", "item_price": overflow if field == "item_price" else "12.3456"}],
    }
    valid = {
        "purchase_date": "2026-10-22",
        "total": maximum,
        "items": [{"item_name": "Молоко", "item_price": maximum}],
    }
    with scripted_server([(200, completion(invalid)), (200, completion(valid))]) as (server, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            structurer = QwenReceiptDataStructurer(client)
            with pytest.raises(FileProcessingError, match="qwen_invalid_receipt_data"):
                structurer.structure(recognition())
            following = structurer.structure(recognition())
            assert following.total == Money(10**38 - 1)
            assert following.items[0].item_price == Money(10**38 - 1)
            assert len(server.requests) == 2
        finally:
            client.close()


@pytest.mark.parametrize("text", ["milk\x00bread", "\ud800"])
@pytest.mark.parametrize("field", ["item_name", "reason"])
def test_qwen_rejects_text_unsafe_for_storage_and_delivery(field, text):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    if field == "reason":
        value = {"is_receipt": False, "reason": text}
    else:
        value = {"purchase_date": None, "total": None, "items": [{"item_name": text, "item_price": None}]}
    with scripted_server([(200, completion(value))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            with pytest.raises(FileProcessingError, match="qwen_invalid_receipt_"):
                if field == "reason":
                    QwenReceiptClassifier(client).classify(recognition())
                else:
                    QwenReceiptDataStructurer(client).structure(recognition())
        finally:
            client.close()


@pytest.mark.parametrize(
    "source,model_date,expected",
    [
        ("22.10+226", "2022-10-22", None),
        ("22.10+2026", "2026-10-22", date(2026, 10, 22)),
        ("Дата: 2025-03-04 12:34", "2025-03-04", date(2025, 3, 4)),
        ("31 / 12 / 1999", "1999-12-31", date(1999, 12, 31)),
        ("1.2.2024", "2024-02-01", date(2024, 2, 1)),
        ("01 02 2024", "2024-02-01", date(2024, 2, 1)),
        ("23.07.25 15:43", "2025-07-23", date(2025, 7, 23)),
        ("ДАТА ВЫДАЧИ 22.10.26 17:22", "2026-10-22", date(2026, 10, 22)),
        ("1/2/2024 09:05", "2024-02-01", date(2024, 2, 1)),
        ("23-07-2025", "2025-07-23", date(2025, 7, 23)),
        ("31.12.99", "2099-12-31", date(2099, 12, 31)),
        ("01.01.00", "2000-01-01", date(2000, 1, 1)),
        ("31.12.99", "1999-12-31", None),
        ("23.07.25", "2026-07-23", None),
        ("122.10.26", "2026-10-22", None),
        ("22.10.260", "2026-10-22", None),
        ("122.10.2026", "2026-10-22", None),
        ("22.10.20260", "2026-10-22", None),
        ("22.10.2027", "2026-10-22", None),
        ("Дата не читается", "2026-10-22", None),
    ],
)
def test_qwen_date_requires_complete_matching_digits_in_recognized_text(source, model_date, expected):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    value = {"purchase_date": model_date, "total": None, "items": []}
    text = RecognitionResult((TextLine(1, 0, source, (0, 0, 500, 20)),))
    with scripted_server([(200, completion(value))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            assert QwenReceiptDataStructurer(client).structure(text).purchase_date == expected
        finally:
            client.close()


@pytest.mark.parametrize("source", ["23.07.25 15:43", "Дата/Номер док. основания\n21.11.2023/1944"])
def test_qwen_null_date_does_not_choose_a_date_from_the_source(source):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    value = {"purchase_date": None, "total": None, "items": []}
    text = RecognitionResult((TextLine(1, 0, source, (0, 0, 500, 20)),))
    with scripted_server([(200, completion(value))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            assert QwenReceiptDataStructurer(client).structure(text).purchase_date is None
        finally:
            client.close()


@pytest.mark.parametrize("model_date", ["2025-02-29", "2025-02-31"])
def test_qwen_rejects_nonexistent_calendar_dates(model_date):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    value = {"purchase_date": model_date, "total": None, "items": []}
    with scripted_server([(200, completion(value))]) as (_, url):
        client = QwenClient(url + "/v1", "qwen", timeout=2)
        try:
            with pytest.raises(FileProcessingError, match="qwen_invalid_receipt_data"):
                QwenReceiptDataStructurer(client).structure(recognition())
        finally:
            client.close()


@pytest.mark.skipif(not os.getenv("TEST_QWEN_URL"), reason="TEST_QWEN_URL required for actual model")
@pytest.mark.parametrize(
    "texts,last_box",
    [
        (("КАССОВЫЙ ЧЕК", "22.10.2026", "Молоко 89.90", "Хлеб 45.10", "ИТОГ 135.00"), (0, 80, 500, 100)),
        (
            ("КАССОВЫЙ ЧЕК", "ООО МАГАЗИН", "22.10.2026", "Молоко     89.90", "Хлеб       45.10", "ИТОГ      135.00"),
            (0, 100, 500, 120),
        ),
    ],
)
def test_live_qwen_extracts_total_from_separate_receipt_lines(texts, last_box):
    from receipt_bot.adapters.recognition.qwen_client import QwenClient
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer

    lines = tuple(TextLine(1, index, text, (0, index * 20, 500, (index + 1) * 20)) for index, text in enumerate(texts))
    recognition = RecognitionResult(lines)
    client = QwenClient(os.environ["TEST_QWEN_URL"], "qwen3-1.7b", timeout=120)
    try:
        data = QwenReceiptDataStructurer(client).structure(recognition)
        assert data.purchase_date == date(2026, 10, 22)
        assert data.total == Money(1350000)
        assert [(item.item_name, item.item_price) for item in data.items] == [
            ("Молоко", Money(899000)),
            ("Хлеб", Money(451000)),
        ]
        assert recognition.lines == lines
        assert recognition.lines[-1].box == last_box
    finally:
        client.close()
