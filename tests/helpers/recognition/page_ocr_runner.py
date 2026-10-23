from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.text_line import TextLine


class PageOCRRunner:
    def recognize(self, image, page_number=1, width=None, height=None):
        assert width == 100 and height == 200
        assert image == {2: b"page-two", 3: b"page-three"}[page_number]
        return RecognitionResult((TextLine(page_number, 0, "OCR", (2, 3, 4, 5)),))
