from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.messaging.attachment_downloader import AttachmentDownloader
from receipt_bot.application.messaging.attachment_reference import AttachmentReference
from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.receipts.expense_repository import ExpenseRepository
from receipt_bot.application.receipts.file_processing_result import FileProcessingResult
from receipt_bot.application.receipts.processing_summary import ProcessingSummary
from receipt_bot.application.receipts.receipt_saver import ReceiptSaver
from receipt_bot.application.receipts.stored_receipt import StoredReceipt
from receipt_bot.application.recognition.receipt_classifier import ReceiptClassifier
from receipt_bot.application.recognition.receipt_data_structurer import ReceiptDataStructurer
from receipt_bot.application.recognition.receipt_item_classificator import ReceiptItemClassificator
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.domain.receipts.receipt_issues import receipt_issues


class MessageProcessor:
    """Обрабатывает каждый файл независимо."""

    def __init__(
        self,
        repository: ExpenseRepository,
        downloader: AttachmentDownloader,
        extractor: ReceiptTextExtractor,
        classifier: ReceiptClassifier,
        structurer: ReceiptDataStructurer,
        item_classificator: ReceiptItemClassificator,
        saver: ReceiptSaver,
        max_attachments: int = 8,
        max_file_bytes: int = 10 * 1024 * 1024,
    ):
        self.repository = repository
        self.downloader = downloader
        self.extractor = extractor
        self.classifier = classifier
        self.structurer = structurer
        self.item_classificator = item_classificator
        self.saver = saver
        self.max_attachments = max_attachments
        self.max_file_bytes = max_file_bytes

    def process(self, message: IncomingMessage) -> ProcessingSummary:
        results = []
        for index, reference in enumerate(message.attachments):
            try:
                if index >= self.max_attachments:
                    raise FileProcessingError("too_many_attachments")
                result = self._process_file(message.owner_id, reference)
            except FileProcessingError as error:
                result = FileProcessingResult(reference, "error", f"Не удалось обработать файл ({error.code}).")
            results.append(result)
        return ProcessingSummary(tuple(results))

    def _process_file(self, owner_id: int, reference: AttachmentReference) -> FileProcessingResult:
        stored = self.repository.find_by_source(owner_id, reference.source_key)
        if stored is not None:
            return self._saved_result(owner_id, reference, stored)
        if reference.size_bytes is not None and reference.size_bytes > self.max_file_bytes:
            raise FileProcessingError("file_too_large")
        attachment = self.downloader.download(reference)
        if len(attachment.content) > self.max_file_bytes:
            raise FileProcessingError("file_too_large")
        recognition = self.extractor.extract(attachment)
        decision = self.classifier.classify(recognition)
        if not decision.is_receipt:
            return FileProcessingResult(reference, "skipped", decision.reason)
        data = self.structurer.structure(recognition)
        issues = receipt_issues(data)
        categories = []
        if not issues:
            for item in data.items:
                categories.append(self.item_classificator.classify_item(item, self.saver.categories))
        stored = self.saver.save(owner_id, reference.source_key, data, tuple(categories), issues)
        return self._saved_result(owner_id, reference, stored)

    def _saved_result(
        self, owner_id: int, reference: AttachmentReference, stored: StoredReceipt
    ) -> FileProcessingResult:
        if stored.receipt.owner_id != owner_id or stored.receipt.source_key != reference.source_key:
            raise StorageError("stored_receipt_mismatch")
        reportable = stored.receipt.is_reportable
        tasks = []
        item_ids = {item.id for item in stored.receipt.items}
        for task in stored.review_tasks:
            if task.owner_id != owner_id or task.item_id not in item_ids:
                raise StorageError("stored_receipt_mismatch")
            if task.status == "pending" and reportable:
                tasks.append(task)
        if reportable:
            status = "saved"
            explanation = "Чек сохранён."
        else:
            status = "draft"
            explanation = "; ".join(stored.receipt.review_reasons)
            explanation += ". Отправьте читаемое вложение новым сообщением с /receipt."
        return FileProcessingResult(reference, status, explanation, stored.receipt, tuple(tasks))
