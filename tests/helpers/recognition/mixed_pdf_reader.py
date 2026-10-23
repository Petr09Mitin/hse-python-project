from receipt_bot.application.recognition.document_page import DocumentPage
from receipt_bot.domain.recognition.text_line import TextLine


class MixedPDFReader:
    def read(self, attachment):
        return (
            DocumentPage(1, (TextLine(1, 0, "Слой", (1, 2, 10, 20)),), 100, 200),
            DocumentPage(2, (), 100, 200, b"page-two"),
            DocumentPage(3, (TextLine(3, 0, "Повреждённый", (1, 1, 2, 2)),), 100, 200, b"page-three", False),
        )
