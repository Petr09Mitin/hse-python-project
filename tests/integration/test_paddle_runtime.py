import os
from io import BytesIO
from pathlib import Path

import pytest


def test_real_cpu_ocr_recognizes_image_with_offline_pinned_models():
    from receipt_bot.adapters.recognition.paddle_ocr_runner import PaddleOCRRunner

    directory = os.environ.get("TEST_OCR_MODEL_DIR")
    if directory is None:
        pytest.skip("Native OCR проверяется в Linux-контейнере make test")
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 48)
    with Image.new("RGB", (1200, 700), "white") as picture, BytesIO() as output:
        draw = ImageDraw.Draw(picture)
        lines = [
            "КАССОВЫЙ ЧЕК",
            "ООО МАГАЗИН",
            "22.10.2026",
            "Молоко     89.90",
            "Хлеб       45.10",
            "ИТОГО     135.00",
        ]
        for index, line in enumerate(lines):
            draw.text((55, 40 + index * 100), line, font=font, fill="black")
        picture.save(output, format="PNG")
        image = output.getvalue()
    root = Path(directory)
    ocr = PaddleOCRRunner(str(root / "PP-OCRv3_mobile_det"), str(root / "cyrillic_PP-OCRv3_mobile_rec"), timeout=60)
    recognition = ocr.recognize(image)
    text = "\n".join(line.text for line in recognition.lines)
    for expected in ("22.10.2026", "Молоко", "Хлеб", "89.90", "45.10", "135.00"):
        assert expected in text
    assert all(line.box[2] <= 1200 and line.box[3] <= 700 for line in recognition.lines)
