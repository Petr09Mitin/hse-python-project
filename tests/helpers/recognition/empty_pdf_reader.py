from receipt_bot.application.recognition.document_page import DocumentPage


class EmptyPDFReader:
    def read(self, attachment):
        return (DocumentPage(1, (), 10, 20),)
