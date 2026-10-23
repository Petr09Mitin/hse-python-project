import math
from io import BytesIO
from pathlib import Path
from threading import Lock

from receipt_bot.adapters.recognition.native_operation import run_native
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.recognition.ocr_runner import OCRRunner
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.text_line import TextLine


def map_prediction(predictions, page_number: int, image_size: tuple, width, height) -> RecognitionResult:
    """Преобразует ответ OCR в строки с координатами страницы."""
    image_width, image_height = image_size
    target_width = image_width if width is None else width
    target_height = image_height if height is None else height
    lines = []
    try:
        for prediction in predictions:
            texts, scores, polygons = prediction["rec_texts"], prediction["rec_scores"], prediction["rec_polys"]
            for text, score, polygon in zip(texts, scores, polygons, strict=True):
                if not isinstance(text, str) or not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
                    raise ValueError("Неверная строка OCR")
                if not text.strip():
                    continue
                if len(polygon) < 4:
                    raise ValueError("Неверный полигон OCR")
                xs, ys = [], []
                for point in polygon:
                    x, y = float(point[0]), float(point[1])
                    if not math.isfinite(x) or not math.isfinite(y):
                        raise ValueError("Неверные координаты OCR")
                    xs.append(min(max(x, 0), image_width) * target_width / image_width)
                    ys.append(min(max(y, 0), image_height) * target_height / image_height)
                lines.append(TextLine(page_number, len(lines), text, (min(xs), min(ys), max(xs), max(ys))))
        return RecognitionResult(tuple(lines))
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as error:
        raise FileProcessingError("ocr_invalid_response") from error


def _recognize(
    image: bytes, page_number: int, width, height, detector_dir: str, recognizer_dir: str
) -> RecognitionResult:
    import numpy as np
    from paddleocr import PaddleOCR
    from PIL import Image

    with Image.open(BytesIO(image)) as source:
        if source.width * source.height > 20_000_000:
            raise FileProcessingError("ocr_image_limit")
        image_size = source.size
        pixels = np.asarray(source.convert("RGB"))[:, :, ::-1].copy()
    engine = PaddleOCR(
        device="cpu",
        cpu_threads=2,
        text_detection_model_name="PP-OCRv3_mobile_det",
        text_detection_model_dir=detector_dir,
        text_recognition_model_name="cyrillic_PP-OCRv3_mobile_rec",
        text_recognition_model_dir=recognizer_dir,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        text_recognition_batch_size=4,
    )
    return map_prediction(engine.predict(pixels), page_number, image_size, width, height)


class PaddleOCRRunner(OCRRunner):
    """Распознаёт текст по одной операции с ограничением времени."""

    def __init__(self, detector_dir: str, recognizer_dir: str, timeout: float = 120):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Таймаут OCR должен быть положительным")
        for directory in (detector_dir, recognizer_dir):
            if not Path(directory).is_dir():
                raise ValueError("Каталог OCR-модели отсутствует")
        self.detector_dir = str(detector_dir)
        self.recognizer_dir = str(recognizer_dir)
        self.timeout = timeout
        self.lock = Lock()

    def recognize(
        self, image: bytes, page_number: int = 1, width: float | None = None, height: float | None = None
    ) -> RecognitionResult:
        if not self.lock.acquire(timeout=self.timeout):
            raise FileProcessingError("ocr_busy")
        try:
            # shortcut: модель загружается заново (~2 с); постоянный процесс нужен при подтверждённой нехватке скорости.
            return run_native(
                _recognize, (image, page_number, width, height, self.detector_dir, self.recognizer_dir), self.timeout
            )
        finally:
            self.lock.release()
