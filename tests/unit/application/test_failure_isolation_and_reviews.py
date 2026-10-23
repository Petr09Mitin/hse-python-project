from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event

import pytest

from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
from receipt_bot.application.categories.review_choice import ReviewChoice
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.messaging.attachment import Attachment
from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
from receipt_bot.application.recognition.document_page import DocumentPage
from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.text_line import TextLine
from tests.helpers.messaging.memory_sender import MemorySender
from tests.helpers.receipts.receipt_scenarios import make_flow, message
from tests.helpers.recognition.mixed_pdf_reader import MixedPDFReader
from tests.helpers.recognition.page_ocr_runner import PageOCRRunner


def test_invalid_model_response_is_a_file_error_and_next_file_is_saved(monkeypatch):
    processor, repository, ports = make_flow()
    structure = ports.structure
    attempts = []

    def structure_next(recognition):
        attempts.append(True)
        if len(attempts) == 1:
            raise FileProcessingError("invalid_json")
        return structure(recognition)

    monkeypatch.setattr(ports, "structure", structure_next)
    summary = processor.process(message("bad", "good"))
    assert [result.status for result in summary.files] == ["error", "saved"]
    assert "invalid_json" in summary.files[0].explanation
    assert summary.accounted_total == Money(30001)
    assert len(repository.receipts) == 1


@pytest.mark.parametrize("orders", [(1, 0), (0, 0)])
def test_invalid_pdf_line_order_is_a_file_error_and_next_photo_is_saved(monkeypatch, orders):
    processor, repository, ports = make_flow()
    page = DocumentPage(
        1,
        (TextLine(1, orders[0], "Первая", (0, 0, 5, 5)), TextLine(1, orders[1], "Вторая", (0, 6, 5, 10))),
        100,
        100,
    )
    monkeypatch.setattr(ports, "read", lambda attachment: (page,))
    request = message("bad", "good")
    pdf = replace(request.attachments[0], file_name="bad.pdf", media_type="application/pdf")
    request = replace(request, attachments=(pdf, request.attachments[1]))
    summary = processor.process(request)
    assert [result.status for result in summary.files] == ["error", "saved"]
    assert "invalid_line_order" in summary.files[0].explanation
    assert summary.files[1].reference.file_name == "good.jpg"
    assert summary.accounted_total == Money(30001)
    assert len(repository.receipts) == 1


def test_storage_failure_during_save_escapes_file_error_isolation(monkeypatch):
    processor, repository, _ports = make_flow()

    def failed_save(receipt, review_tasks):
        raise StorageError("write_failed")

    monkeypatch.setattr(repository, "save", failed_save)
    with pytest.raises(StorageError, match="write_failed"):
        processor.process(message("a", "b"))
    assert repository.receipts == {}


def test_attachment_count_limit_preserves_results_for_accepted_files():
    processor, repository, _ports = make_flow()
    processor.max_attachments = 1
    summary = processor.process(message("first", "extra"))
    assert [result.status for result in summary.files] == ["saved", "error"]
    assert "too_many_attachments" in summary.files[1].explanation
    assert len(repository.receipts) == 1


def test_announced_size_limit_prevents_download():
    processor, repository, ports = make_flow()
    reference = replace(message("a").attachments[0], size_bytes=processor.max_file_bytes + 1)
    result = processor.process(replace(message("a"), attachments=(reference,))).files[0]
    assert result.status == "error"
    assert "file_too_large" in result.explanation
    assert ports.calls == []
    assert repository.receipts == {}


def test_downloaded_size_is_checked_even_when_metadata_is_missing():
    processor, repository, ports = make_flow()
    processor.max_file_bytes = 4
    result = processor.process(message("a")).files[0]
    assert result.status == "error"
    assert "file_too_large" in result.explanation
    assert ports.calls == [("download", "a")]
    assert repository.receipts == {}


def test_pdf_page_limit_prevents_ocr():
    extractor = ReceiptTextExtractor(MixedPDFReader(), PageOCRRunner(), max_pages=1)
    with pytest.raises(FileProcessingError, match="too_many_pages"):
        extractor.extract(Attachment("a.pdf", "application/pdf", b"pdf"))


def test_regrouped_album_returns_the_original_source_and_pending_task():
    processor, repository, ports = make_flow()
    original_message = message("a")
    first = processor.process(original_message).files[0]
    ports.calls.clear()
    regrouped = replace(original_message, event_id="different-album", acknowledgement_ids=("event", "new"))
    repeated = processor.process(regrouped).files[0]
    assert repeated.receipt == first.receipt
    assert repeated.review_tasks == first.review_tasks
    assert ports.calls == []
    assert len(repository.receipts) == 1


def test_same_source_is_independent_for_each_owner():
    processor, repository, _ports = make_flow()
    first = processor.process(message("a")).files[0]
    second = processor.process(message("a", owner_id=2)).files[0]
    assert first.receipt.owner_id == 1
    assert second.receipt.owner_id == 2
    assert first.receipt.id != second.receipt.id
    assert len(repository.receipts) == 2


def test_review_rejects_foreign_invalid_and_repeated_choices_without_overwriting():
    processor, repository, _ports = make_flow()
    result = processor.process(message("a")).files[0]
    task = result.review_tasks[0]
    reviewer = CategoryReviewProcessor(repository)
    assert "недоступна" in reviewer.process(2, ReviewChoice(task.id, "health"))
    reviewer.process(1, ReviewChoice(task.id, "unknown"))
    assert repository.tasks[task.id].status == "pending"
    assert repository.find_by_source(1, result.reference.source_key).receipt.items[1].category is None
    reviewer.process(1, ReviewChoice(task.id, "health"))
    repeat = reviewer.process(1, ReviewChoice(task.id, "transport"))
    assert "уже" in repeat.lower()
    stored = repository.find_by_source(1, result.reference.source_key)
    assert stored.receipt.items[1].category == DEFAULT_CATEGORIES[3]
    assert stored.receipt.items[1].created_at == result.receipt.items[1].created_at
    assert stored.review_tasks[0].status == "answered"


def test_competing_review_winner_is_preserved_when_atomic_update_returns_false(monkeypatch):
    processor, repository, _ports = make_flow()
    result = processor.process(message("a")).files[0]
    task = result.review_tasks[0]
    original_answer = repository.answer_review

    def competing_answer(owner_id, task_id, category, answered_at):
        original_answer(owner_id, task_id, DEFAULT_CATEGORIES[1], datetime.now(UTC))
        return original_answer(owner_id, task_id, category, answered_at)

    monkeypatch.setattr(repository, "answer_review", competing_answer)
    response = CategoryReviewProcessor(repository).process(1, ReviewChoice(task.id, "health"))
    assert "уже" in response.lower()
    stored = repository.find_by_source(1, result.reference.source_key)
    assert stored.receipt.items[1].category == DEFAULT_CATEGORIES[1]
    assert stored.review_tasks[0].answer_category == DEFAULT_CATEGORIES[1]


def test_same_owner_can_answer_category_while_another_receipt_is_in_ocr(monkeypatch):
    processor, repository, ports = make_flow()
    saved = processor.process(message("a")).files[0]
    sender = MemorySender()
    dispatcher = MessageDispatcher(processor, CategoryReviewProcessor(repository), None, sender)
    new_reference = replace(message("b").attachments[0], source_event_id="new-receipt")
    new_message = replace(message("b"), event_id="new-receipt", attachments=(new_reference,))
    callback = replace(message(), event_id="answer", review_choice=ReviewChoice(saved.review_tasks[0].id, "health"))
    receipt_work = dispatcher.prepare(new_message)
    review_work = dispatcher.prepare(callback)
    started = Event()
    release = Event()
    recognize = ports.recognize

    def blocked_recognize(*args, **kwargs):
        started.set()
        assert release.wait(timeout=3)
        return recognize(*args, **kwargs)

    monkeypatch.setattr(ports, "recognize", blocked_recognize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipt_future = pool.submit(dispatcher.dispatch, receipt_work)
        try:
            assert started.wait(timeout=2)
            review_future = pool.submit(dispatcher.dispatch, review_work)
            assert review_future.result(timeout=2)[0].status == "delivered"
            assert repository.tasks[saved.review_tasks[0].id].answer_category == DEFAULT_CATEGORIES[3]
        finally:
            release.set()
        assert all(outcome.status == "delivered" for outcome in receipt_future.result(timeout=2))
