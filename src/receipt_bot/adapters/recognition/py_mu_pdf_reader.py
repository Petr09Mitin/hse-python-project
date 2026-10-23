import math

from receipt_bot.adapters.recognition.native_operation import run_native
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.recognition.document_page import DocumentPage
from receipt_bot.application.recognition.pdf_reader import PDFReader
from receipt_bot.domain.recognition.text_line import TextLine


def _read_pdf(content: bytes, max_pages: int) -> tuple[DocumentPage, ...]:
    import pymupdf

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise FileProcessingError("pdf_encrypted")
            if len(document) > max_pages:
                raise FileProcessingError("pdf_page_limit")
            pages = []
            remaining_pixels = 40_000_000
            for number, page in enumerate(document, start=1):
                if any(not math.isfinite(size) or size <= 0 for size in (page.rect.width, page.rect.height)):
                    raise FileProcessingError("pdf_invalid")
                lines = []
                for block in page.get_text("dict", sort=True)["blocks"]:
                    for raw in block.get("lines", []):
                        text = "".join(span["text"] for span in raw["spans"]).strip()
                        if text:
                            box = pymupdf.Rect(raw["bbox"]) * page.rotation_matrix
                            box = box & page.rect
                            if any(not math.isfinite(value) for value in box) or box.is_empty:
                                raise FileProcessingError("pdf_invalid")
                            lines.append(TextLine(number, len(lines), text, (box.x0, box.y0, box.x1, box.y1)))
                text = " ".join(line.text for line in lines)
                usable = sum(character.isalnum() for character in text) >= 3 and text.count("\ufffd") <= len(text) // 20
                if len(text) < 100 and any(
                    (pymupdf.Rect(image["bbox"]) * page.rotation_matrix & page.rect).get_area()
                    >= page.rect.get_area() / 2
                    for image in page.get_image_info()
                ):
                    usable = False
                image = None
                if not usable:
                    pixels = math.ceil(page.rect.width * 2) * math.ceil(page.rect.height * 2)
                    if pixels > remaining_pixels:
                        raise FileProcessingError("pdf_render_limit")
                    remaining_pixels -= pixels
                    image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")
                pages.append(DocumentPage(number, tuple(lines), page.rect.width, page.rect.height, image, usable))
            if not pages:
                raise FileProcessingError("pdf_empty")
            return tuple(pages)
    except (ValueError, RuntimeError) as error:
        raise FileProcessingError("pdf_invalid") from error


class PyMuPDFReader(PDFReader):
    """Извлекает текст PDF и готовит изображения страниц для OCR."""

    def __init__(self, max_pages: int = 20, timeout: float = 30):
        if type(max_pages) is not int or not 1 <= max_pages <= 20 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Некорректные лимиты PDF")
        self.max_pages = max_pages
        self.timeout = timeout

    def read(self, attachment: Attachment) -> tuple[DocumentPage, ...]:
        if attachment.media_type != "application/pdf":
            raise FileProcessingError("pdf_type_required")
        return run_native(_read_pdf, (attachment.content, self.max_pages), self.timeout)
