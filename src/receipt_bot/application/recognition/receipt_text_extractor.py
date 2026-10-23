from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.recognition.ocr_runner import OCRRunner
from receipt_bot.application.recognition.pdf_reader import PDFReader
from receipt_bot.domain.recognition.recognition_result import RecognitionResult


class ReceiptTextExtractor:
    """Выбирает текст или OCR отдельно для каждой страницы."""

    def __init__(self, pdf_reader: PDFReader, ocr_runner: OCRRunner, max_pages: int = 20):
        self.pdf_reader = pdf_reader
        self.ocr_runner = ocr_runner
        self.max_pages = max_pages

    def extract(self, attachment: Attachment) -> RecognitionResult:
        if attachment.media_type.startswith("image/"):
            result = self.ocr_runner.recognize(attachment.content)
            if not result.lines:
                raise FileProcessingError("empty_recognition")
            return result
        if attachment.media_type != "application/pdf":
            raise FileProcessingError("unsupported_format")
        pages = self.pdf_reader.read(attachment)
        if not pages:
            raise FileProcessingError("empty_pdf")
        if len(pages) > self.max_pages:
            raise FileProcessingError("too_many_pages")
        lines = []
        for expected_number, page in enumerate(pages, start=1):
            if page.page_number != expected_number:
                raise FileProcessingError("invalid_page_order")
            if page.text_usable and page.text_lines:
                page_lines = page.text_lines
            else:
                if page.image is None:
                    raise FileProcessingError("missing_page_image")
                page_lines = self.ocr_runner.recognize(page.image, page.page_number, page.width, page.height).lines
            for line in page_lines:
                if line.page_number != page.page_number or line.box[2] > page.width or line.box[3] > page.height:
                    raise FileProcessingError("invalid_page_coordinates")
                lines.append(line)
        if not lines:
            raise FileProcessingError("empty_recognition")
        previous = (0, -1)
        for line in lines:
            position = (line.page_number, line.order)
            if position <= previous:
                raise FileProcessingError("invalid_line_order")
            previous = position
        return RecognitionResult(tuple(lines))
