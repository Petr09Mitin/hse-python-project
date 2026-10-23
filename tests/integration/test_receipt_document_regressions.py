import os
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

import pytest

from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader
from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner
from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.receipts.message_processor import MessageProcessor
from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.text_line import TextLine
from tests.helpers.receipts.memory_expenses import MemoryExpenses
from tests.helpers.receipts.receipt_scenarios import message

API_CONFIGURED = all(os.getenv(name) for name in ("TEST_OPENAI_BASE_URL", "TEST_OPENAI_MODEL", "TEST_OPENAI_API_KEY"))


@pytest.fixture(scope="module")
def api_client():
    if not API_CONFIGURED:
        pytest.skip("Нужны TEST_OPENAI_* для явной проверки внешней модели")
    client = QwenClient(
        os.environ["TEST_OPENAI_BASE_URL"],
        os.environ["TEST_OPENAI_MODEL"],
        timeout=60,
        max_attempts=1,
        max_tokens=8192,
        api_key=os.environ["TEST_OPENAI_API_KEY"],
    )
    request = client.request
    last_request = 0.0

    def paced_request(name, schema, prompt, image_url=None):
        nonlocal last_request
        # Общий прогон с категориями превышает 20 вызовов: оставляем запас к минутному лимиту API.
        delay = 4 - (monotonic() - last_request)
        if delay > 0:
            sleep(delay)
        last_request = monotonic()
        return request(name, schema, prompt, image_url=image_url)

    client.request = paced_request
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize(
    "path_key,expected_date,expected_prices",
    [
        ("TEST_SHORT_YEAR_PHOTO", date(2025, 7, 23), (800000,)),
        ("TEST_SHORT_YEAR_PDF", date(2026, 10, 22), (3600000, 3600000)),
        (
            "TEST_GUEST_BILL_PHOTO",
            date(2026, 9, 9),
            (8800000, 9400000, 18000000, 11800000, 10400000, 8200000, 5200000, 5400000, 11000000),
        ),
    ],
    ids=["short-year-photo", "short-year-pdf", "restaurant-guest-bill"],
)
def test_live_document_becomes_reportable_receipt(api_client, path_key, expected_date, expected_prices):
    """Читает только явно указанные внешние файлы, сохраняет результат лишь в памяти."""
    source = os.getenv(path_key)
    if not source:
        pytest.skip(f"Нужен путь {path_key} к разрешённому для API документу")
    path = Path(source)
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
    attachment = Attachment(path.name, media_type, path.read_bytes())
    repository = MemoryExpenses()
    processor = MessageProcessor(
        repository,
        SimpleNamespace(download=lambda reference: attachment),
        ReceiptTextExtractor(PyMuPDFReader(), QwenOCRRunner(api_client)),
        QwenReceiptClassifier(api_client),
        QwenReceiptDataStructurer(api_client),
        QwenReceiptItemClassificator(api_client),
        ReceiptSaver(repository),
    )

    summary = processor.process(message("document"))

    assert summary.files[0].status == "saved", summary.files[0].explanation
    receipt = summary.files[0].receipt
    assert receipt.is_reportable
    assert receipt.purchase_date == expected_date
    assert [item.item_price.units for item in receipt.items] == list(expected_prices)
    assert receipt.total == Money(sum(expected_prices))
    assert summary.accounted_total == receipt.total
    if path_key == "TEST_GUEST_BILL_PHOTO":
        assert receipt.items[4].item_name.startswith("Утка")
        assert receipt.items[4].item_name.endswith("манер")


@pytest.mark.parametrize(
    "text,is_receipt",
    [
        (
            (
                "ГОСТЕВОЙ СЧЕТ\nОткрыт: 09.09.2026 21:14\nСтол: 22\nЗаказ № 125693\n"
                "Наименование Кол-во Сумма\nКарпаччо 1 940,00\nБрауни 2 1 100,00\nИТОГО К ОПЛАТЕ: 2 040,00"
            ),
            True,
        ),
        ("МЕНЮ\nКарпаччо 940,00\nБрауни 550,00\nЦены действуют с 09.09.2026", False),
        ("Прайс-лист\nМолоко 100,00\nХлеб 80,00\nЦены указаны за единицу товара", False),
        ("Банковская выписка\n09.09.2026 Перевод между своими счетами 2040,00", False),
    ],
    ids=["guest-bill", "menu", "price-list", "bank-transfer"],
)
def test_live_document_classifier_accepts_guest_bill_but_rejects_catalogs_and_transfers(api_client, text, is_receipt):
    recognition = RecognitionResult((TextLine(1, 0, text, (0, 0, 1000, 1000)),))
    assert QwenReceiptClassifier(api_client).classify(recognition).is_receipt is is_receipt
