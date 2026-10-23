from datetime import date

from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.receipt_decision import ReceiptDecision
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData
from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData
from receipt_bot.domain.recognition.text_line import TextLine


class RecognitionPorts:
    def __init__(self):
        self.calls = []
        self.data = StructuredReceiptData(
            date(2026, 10, 20),
            Money(30001),
            (StructuredItemData("Хлеб", Money(10000)), StructuredItemData("Молоко", Money(20001))),
        )
        self.decision = ReceiptDecision(True, "Покупка")
        self.failed_tokens = set()

    def download(self, reference):
        from receipt_bot.application.errors.file_processing_error import FileProcessingError
        from receipt_bot.application.messaging.attachment import Attachment

        self.calls.append(("download", reference.source_token))
        if reference.source_token in self.failed_tokens:
            raise FileProcessingError("download_failed")
        return Attachment(reference.file_name, reference.media_type, b"image")

    def recognize(self, image, page_number=1, width=None, height=None):
        self.calls.append(("ocr", page_number))
        return RecognitionResult((TextLine(page_number, 0, "Текст", (0, 0, 5, 5)),))

    def classify(self, recognition):
        self.calls.append(("classify",))
        return self.decision

    def structure(self, recognition):
        self.calls.append(("structure",))
        return self.data

    def classify_item(self, item, categories):
        self.calls.append(("category", item.item_name))
        if item.item_name == "Хлеб":
            return DEFAULT_CATEGORIES[0]
        return None

    def read(self, attachment):
        raise AssertionError("Фотография не должна попадать в обработчик PDF")
