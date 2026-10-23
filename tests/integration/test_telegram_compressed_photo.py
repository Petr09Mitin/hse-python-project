import os
from pathlib import Path

import pytest

from receipt_bot.adapters.recognition.paddle_ocr_runner import PaddleOCRRunner
from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
from receipt_bot.domain.money import Money
from receipt_bot.domain.receipts.receipt_issues import receipt_issues
from tests.helpers.receipts.memory_expenses import MemoryExpenses


@pytest.mark.skipif(
    not all(os.getenv(key) for key in ("TEST_OCR_MODEL_DIR", "TEST_QWEN_URL")), reason="Linux OCR and Qwen required"
)
def test_telegram_compressed_photo_with_incomplete_year_is_saved_as_draft():
    root = Path(os.environ["TEST_OCR_MODEL_DIR"])
    ocr = PaddleOCRRunner(str(root / "PP-OCRv3_mobile_det"), str(root / "cyrillic_PP-OCRv3_mobile_rec"), timeout=120)
    fixture = Path(__file__).parents[1] / "fixtures" / "telegram-compressed.jpeg"
    recognition = ocr.recognize(fixture.read_bytes())
    client = QwenClient(os.environ["TEST_QWEN_URL"], "qwen3-1.7b", timeout=120)
    try:
        data = QwenReceiptDataStructurer(client).structure(recognition)
    finally:
        client.close()
    stored = ReceiptSaver(MemoryExpenses()).save(
        1, "telegram-compressed", data, (None,) * len(data.items), receipt_issues(data)
    )
    assert stored.receipt.purchase_date is None
    assert not stored.receipt.is_reportable
    assert "Не удалось прочитать дату покупки" in stored.receipt.review_reasons
    assert stored.review_tasks == ()
    assert stored.receipt.total == Money(1350000)
    assert [item.item_price for item in stored.receipt.items] == [Money(899000), Money(451000)]
