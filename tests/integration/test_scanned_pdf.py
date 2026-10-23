import os
from datetime import date
from pathlib import Path

import pytest

from receipt_bot.adapters.recognition.paddle_ocr_runner import PaddleOCRRunner
from receipt_bot.adapters.recognition.py_mu_pdf_reader import PyMuPDFReader
from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.domain.money import Money
from tests.integration.test_full_stack import image_receipt


@pytest.mark.skipif(
    not all(os.getenv(key) for key in ("TEST_OCR_MODEL_DIR", "TEST_QWEN_URL")), reason="Linux OCR and Qwen required"
)
def test_actual_ocr_reads_receipt_under_short_pdf_footer(monkeypatch):
    import pymupdf

    lines = ("КАССОВЫЙ ЧЕК", "ООО МАГАЗИН", "22.10.2026", "Молоко     89.90", "Хлеб       45.10", "ИТОГО     135.00")
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=390)
        page.insert_image(pymupdf.Rect(0, 0, 600, 350), stream=image_receipt(lines))
        page.insert_text((20, 375), "Page 1 of 1")
        content = document.tobytes()
    root = Path(os.environ["TEST_OCR_MODEL_DIR"])
    ocr = PaddleOCRRunner(str(root / "PP-OCRv3_mobile_det"), str(root / "cyrillic_PP-OCRv3_mobile_rec"), timeout=120)
    calls = []
    original = ocr.recognize

    def observe_ocr(image, page_number=1, width=None, height=None):
        calls.append(page_number)
        return original(image, page_number, width, height)

    monkeypatch.setattr(ocr, "recognize", observe_ocr)
    extractor = ReceiptTextExtractor(PyMuPDFReader(timeout=10), ocr)
    recognition = extractor.extract(Attachment("scan.pdf", "application/pdf", content))
    assert calls == [1]
    text = "\n".join(line.text for line in recognition.lines)
    assert all(expected in text for expected in ("Молоко", "Хлеб", "89.90", "45.10", "135.00")), text
    client = QwenClient(os.environ["TEST_QWEN_URL"], "qwen3-1.7b", timeout=120)
    try:
        data = QwenReceiptDataStructurer(client).structure(recognition)
        assert data.purchase_date == date(2026, 10, 22)
        assert data.total == Money(1350000)
        assert [(item.item_name, item.item_price) for item in data.items] == [
            ("Молоко", Money(899000)),
            ("Хлеб", Money(451000)),
        ]
    finally:
        client.close()
