import base64
import json
import os
from datetime import date

import pymupdf
import pytest

from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.text_line import TextLine
from tests.helpers.http.http_server import scripted_server
from tests.integration.test_qwen_adapters import completion


def image_bytes():
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_text((10, 25), "TOTAL 100.00")
        return page.get_pixmap().tobytes("png")


def test_vision_ocr_sends_image_with_configured_auth_and_maps_pdf_coordinates():
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner

    image = image_bytes()
    value = {"lines": [{"text": "ИТОГ 100.00", "box": [100, 200, 900, 400]}]}
    with scripted_server([(200, completion(value))]) as (server, url):
        client = QwenClient(url + "/v1", "qwen3.6-35b-a3b", timeout=2, api_key="test-api-key")
        try:
            result = QwenOCRRunner(client).recognize(image, page_number=3, width=600, height=800)
            assert result.lines == (TextLine(3, 0, "ИТОГ 100.00", (60, 160, 540, 320)),)
            path, body, headers = server.requests[0]
            assert path == "/v1/chat/completions"
            assert {name.lower(): value for name, value in headers.items()}["authorization"] == "Bearer test-api-key"
            payload = json.loads(body)
            assert payload["model"] == "qwen3.6-35b-a3b"
            content = payload["messages"][1]["content"]
            assert content[0]["type"] == "text"
            assert content[1]["type"] == "image_url"
            prefix, encoded = content[1]["image_url"]["url"].split(",", 1)
            assert prefix == "data:image/png;base64"
            assert base64.b64decode(encoded) == image
        finally:
            client.close()


@pytest.mark.parametrize(
    "line",
    [
        {"text": "ИТОГ", "box": [0, 0, 1001, 100]},
        {"text": "ИТОГ", "box": [100, 0, 0, 100]},
        {"text": "ИТОГ", "box": [False, 0, 100, 100]},
        {"text": "ИТОГ", "box": [0, 0, 100]},
        {"text": "ИТОГ", "box": [0, 0, "100", 100]},
        {"text": "ИТОГ\u0000", "box": [0, 0, 100, 100]},
        {"text": None, "box": [0, 0, 100, 100]},
        {"text": "ИТОГ", "box": [0, 0, 100, 100], "extra": True},
    ],
)
def test_vision_ocr_rejects_invalid_lines_without_losing_next_image(line):
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner

    values = [{"lines": [line]}, {"lines": [{"text": "ИТОГ", "box": [0, 0, 1000, 1000]}]}]
    with scripted_server([(200, completion(value)) for value in values]) as (_, url):
        client = QwenClient(url + "/v1", "vision", timeout=2)
        try:
            ocr = QwenOCRRunner(client)
            with pytest.raises(FileProcessingError, match="ocr_invalid_response"):
                ocr.recognize(image_bytes())
            assert ocr.recognize(image_bytes()).lines == (TextLine(1, 0, "ИТОГ", (0, 0, 200, 100)),)
        finally:
            client.close()


def test_vision_ocr_rejects_bad_image_before_network_call():
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner

    with scripted_server([]) as (server, url):
        client = QwenClient(url + "/v1", "vision", timeout=2)
        try:
            with pytest.raises(FileProcessingError, match="ocr_invalid_image"):
                QwenOCRRunner(client).recognize(b"not an image")
            assert server.requests == []
        finally:
            client.close()


def test_vision_ocr_accepts_cmyk_jpeg_and_sends_rgb_png():
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner

    image = pymupdf.Pixmap(pymupdf.csCMYK, (0, 0, 200, 100), False).tobytes("jpeg")
    value = {"lines": [{"text": "ИТОГ", "box": [0, 0, 1000, 1000]}]}
    with scripted_server([(200, completion(value))]) as (server, url):
        client = QwenClient(url + "/v1", "vision", timeout=2)
        try:
            assert QwenOCRRunner(client).recognize(image).lines == (TextLine(1, 0, "ИТОГ", (0, 0, 200, 100)),)
            content = json.loads(server.requests[0][1])["messages"][1]["content"]
            encoded = content[1]["image_url"]["url"].split(",", 1)[1]
            assert pymupdf.Pixmap(base64.b64decode(encoded)).colorspace.n == 3
        finally:
            client.close()


def test_vision_ocr_rejects_oversized_image_before_decoding_pixels(monkeypatch):
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner

    pixels = pymupdf.Pixmap(pymupdf.csGRAY, (0, 0, 5000, 4001), False)
    pixels.clear_with(255)
    image = pixels.tobytes("png")
    del pixels

    def unexpected_decode(*args):
        pytest.fail("Превышение пиксельного лимита нужно проверять до декодирования")

    monkeypatch.setattr(pymupdf, "Pixmap", unexpected_decode)
    client = QwenClient("http://127.0.0.1/v1", "vision", timeout=2)
    try:
        with pytest.raises(FileProcessingError, match="ocr_image_limit"):
            QwenOCRRunner(client).recognize(image)
    finally:
        client.close()


@pytest.mark.skipif(
    not all(os.getenv(name) for name in ("TEST_OPENAI_BASE_URL", "TEST_OPENAI_MODEL", "TEST_OPENAI_API_KEY")),
    reason="Нужны TEST_OPENAI_* для явной проверки внешней модели",
)
def test_live_api_reads_receipt_image_and_classifies_item():
    from receipt_bot.adapters.recognition.qwen_ocr_runner import QwenOCRRunner
    from receipt_bot.adapters.recognition.qwen_receipt_classifier import QwenReceiptClassifier
    from receipt_bot.adapters.recognition.qwen_receipt_data_structurer import QwenReceiptDataStructurer
    from receipt_bot.adapters.recognition.qwen_receipt_item_classificator import QwenReceiptItemClassificator

    with pymupdf.open() as document:
        page = document.new_page(width=400, height=250)
        page.insert_font(fontname="receipt", fontbuffer=pymupdf.Font("cjk").buffer)
        page.insert_text(
            (30, 35), "КАССОВЫЙ ЧЕК\n22.10.2026\nМолоко 100.00\nИТОГ 100.00", fontname="receipt", fontsize=20
        )
        image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
    client = QwenClient(
        os.environ["TEST_OPENAI_BASE_URL"],
        os.environ["TEST_OPENAI_MODEL"],
        timeout=60,
        max_attempts=1,
        max_tokens=8192,
        api_key=os.environ["TEST_OPENAI_API_KEY"],
    )
    try:
        recognition = QwenOCRRunner(client).recognize(image)
        assert QwenReceiptClassifier(client).classify(recognition).is_receipt
        receipt = QwenReceiptDataStructurer(client).structure(recognition)
        assert receipt.purchase_date == date(2026, 10, 22)
        assert receipt.total == Money(1000000)
        assert len(receipt.items) == 1
        assert receipt.items[0].item_price == Money(1000000)
        category = QwenReceiptItemClassificator(client).classify_item(receipt.items[0], DEFAULT_CATEGORIES)
        assert category == DEFAULT_CATEGORIES[0]
    finally:
        client.close()
