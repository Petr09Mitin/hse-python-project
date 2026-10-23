from tests.helpers.receipts.memory_expenses import MemoryExpenses
from tests.helpers.recognition.recognition_ports import RecognitionPorts


def make_flow():
    from receipt_bot.application.receipts.message_processor import MessageProcessor
    from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
    from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor

    repository = MemoryExpenses()
    ports = RecognitionPorts()
    extractor = ReceiptTextExtractor(ports, ports)
    saver = ReceiptSaver(repository)
    processor = MessageProcessor(repository, ports, extractor, ports, ports, ports, saver)
    return processor, repository, ports


def message(*tokens, owner_id=1):
    from receipt_bot.application.messaging.attachment_reference import AttachmentReference
    from receipt_bot.application.messaging.incoming_message import IncomingMessage

    references = []
    for index, token in enumerate(tokens):
        references.append(AttachmentReference("event", index, token, f"{token}.jpg", "image/jpeg"))
    return IncomingMessage(owner_id, 10, "event", "/receipt", tuple(references))
