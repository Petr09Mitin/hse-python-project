import base64
import math
from decimal import Decimal

import pymupdf

from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_schema import object_schema, text_model
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.recognition.ocr_runner import OCRRunner
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.text_line import TextLine

OCR_SCHEMA = object_schema(
    {
        "lines": {
            "type": "array",
            "items": object_schema(
                {
                    "text": {"type": "string"},
                    "box": {
                        "type": "array",
                        "items": {"type": "number", "minimum": 0, "maximum": 1000},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                }
            ),
        }
    }
)


class QwenOCRRunner(OCRRunner):
    """Распознаёт строки изображения через API модели с поддержкой vision."""

    def __init__(self, client: QwenClient):
        self.client = client

    def recognize(
        self, image: bytes, page_number: int = 1, width: float | None = None, height: float | None = None
    ) -> RecognitionResult:
        try:
            # MuPDF читает размеры до распаковки; image_profile сломан в закреплённом PyMuPDF 1.26.7.
            source = pymupdf.mupdf.fz_new_image_from_buffer(pymupdf.mupdf.fz_new_buffer_from_copied_data(image))
            if source.w() * source.h() > 20_000_000:
                raise FileProcessingError("ocr_image_limit")
            pixels = pymupdf.Pixmap(image)
            if pixels.colorspace.n == 4:
                pixels = pymupdf.Pixmap(pymupdf.csRGB, pixels)
            # PNG даёт одинаковый MIME для фотографий Telegram и отрендеренных PDF-страниц.
            encoded = base64.b64encode(pixels.tobytes("png")).decode("ascii")
        except (RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase) as error:
            raise FileProcessingError("ocr_invalid_image") from error
        target_width = pixels.width if width is None else width
        target_height = pixels.height if height is None else height
        result = self.client.request(
            "receipt_ocr",
            OCR_SCHEMA,
            "Перепиши весь читаемый текст с изображения без исправлений и догадок. "
            "Верни lines в порядке чтения сверху вниз, слева направо. Каждая строка: text и "
            "box=[x0,y0,x1,y1] в координатах от 0 до 1000 относительно ширины и высоты изображения. "
            "Сохраняй даты, цены и итог дословно. Нечитаемые строки пропускай. Если текста нет, верни lines=[].",
            image_url="data:image/png;base64," + encoded,
        )
        try:
            if not isinstance(result["lines"], list):
                raise TypeError("lines")
            lines = []
            for line in result["lines"]:
                if not isinstance(line, dict) or set(line) != {"text", "box"}:
                    raise ValueError("line")
                text = text_model(line["text"])
                box = line["box"]
                if not isinstance(box, list) or len(box) != 4:
                    raise ValueError("box")
                for value in box:
                    if type(value) not in (int, float, Decimal) or not math.isfinite(value) or not 0 <= value <= 1000:
                        raise ValueError("coordinate")
                x0, y0, x1, y1 = map(float, box)
                if x0 >= x1 or y0 >= y1:
                    raise ValueError("box_order")
                coordinates = (
                    x0 * target_width / 1000,
                    y0 * target_height / 1000,
                    x1 * target_width / 1000,
                    y1 * target_height / 1000,
                )
                lines.append(TextLine(page_number, len(lines), text, coordinates))
            return RecognitionResult(tuple(lines))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise FileProcessingError("ocr_invalid_response") from error
