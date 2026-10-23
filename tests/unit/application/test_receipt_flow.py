from dataclasses import replace
from datetime import UTC, datetime

import pytest

from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.receipt_decision import ReceiptDecision
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData
from tests.helpers.receipts.receipt_scenarios import make_flow, message
from tests.helpers.recognition.empty_pdf_reader import EmptyPDFReader
from tests.helpers.recognition.mixed_pdf_reader import MixedPDFReader
from tests.helpers.recognition.page_ocr_runner import PageOCRRunner
from tests.helpers.recognition.recognition_ports import RecognitionPorts

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def test_photo_pipeline_saves_exact_sum_and_pending_category():
    processor, repository, ports = make_flow()
    summary = processor.process(message("a"))
    result = summary.files[0]
    assert result.status == "saved"
    assert summary.accounted_total == Money(30001)
    assert result.receipt.owner_id == 1
    assert result.receipt.items[1].category is None
    assert len(result.review_tasks) == 1
    assert result.review_tasks[0].item_id == result.receipt.items[1].id
    assert result.receipt.items[0].created_at.utcoffset() is not None
    assert ports.calls == [
        ("download", "a"),
        ("ocr", 1),
        ("classify",),
        ("structure",),
        ("category", "Хлеб"),
        ("category", "Молоко"),
    ]
    assert len(repository.receipts) == 1


def test_saved_source_returns_current_manual_category_without_external_calls():
    from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
    from receipt_bot.application.categories.review_choice import ReviewChoice

    processor, repository, ports = make_flow()
    first = processor.process(message("a")).files[0]
    review = CategoryReviewProcessor(repository)
    review.process(1, ReviewChoice(first.review_tasks[0].id, "health"))
    ports.calls.clear()
    ports.failed_tokens.add("a")
    repeated = processor.process(message("a")).files[0]
    assert repeated.receipt.id == first.receipt.id
    assert repeated.receipt.items[1].category == DEFAULT_CATEGORIES[3]
    assert repeated.review_tasks == ()
    assert ports.calls == []


def test_file_failure_does_not_discard_following_receipt():
    processor, repository, ports = make_flow()
    ports.failed_tokens.add("bad")
    summary = processor.process(message("bad", "good"))
    assert [file.status for file in summary.files] == ["error", "saved"]
    assert summary.accounted_total == Money(30001)
    assert "download_failed" in summary.files[0].explanation
    assert len(repository.receipts) == 1


def test_storage_failure_is_not_a_successful_file_result():
    from receipt_bot.application.errors.storage_error import StorageError

    processor, repository, ports = make_flow()
    repository.fail_storage = True
    with pytest.raises(StorageError):
        processor.process(message("a"))
    assert ports.calls == []


def test_non_receipt_is_skipped_before_structuring():
    processor, repository, ports = make_flow()
    ports.decision = ReceiptDecision(False, "Это расписание")
    result = processor.process(message("a")).files[0]
    assert result.status == "skipped"
    assert result.explanation == "Это расписание"
    assert repository.receipts == {}
    assert ports.calls == [("download", "a"), ("ocr", 1), ("classify",)]


@pytest.mark.parametrize("change", ["date", "total", "item_name", "item_price", "mismatch", "empty"])
def test_unreadable_or_inconsistent_finances_remain_excluded_drafts(change):
    processor, repository, ports = make_flow()
    data = ports.data
    if change == "date":
        data = replace(data, purchase_date=None)
    elif change == "total":
        data = replace(data, total=None)
    elif change == "item_name":
        data = replace(data, items=(StructuredItemData(None, Money(30001)),))
    elif change == "item_price":
        data = replace(data, items=(StructuredItemData("Товар", None),))
    elif change == "mismatch":
        data = replace(data, total=Money(1))
    else:
        data = replace(data, items=())
    ports.data = data
    summary = processor.process(message("a"))
    result = summary.files[0]
    assert result.status == "draft"
    assert not result.receipt.is_reportable
    assert result.receipt.review_reasons
    assert summary.accounted_total == Money(0)
    assert result.receipt.purchase_date == data.purchase_date
    assert result.receipt.total == data.total
    assert len(repository.receipts) == 1
    assert result.review_tasks == ()
    assert all(item.category is None for item in result.receipt.items)
    assert not any(call[0] == "category" for call in ports.calls)


def test_financial_draft_asks_for_a_readable_receipt_without_category_buttons():
    from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
    from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
    from tests.helpers.messaging.memory_sender import MemorySender

    processor, repository, ports = make_flow()
    ports.data = replace(ports.data, purchase_date=None)
    sender = MemorySender()
    dispatcher = MessageDispatcher(processor, CategoryReviewProcessor(repository), None, sender)
    dispatcher.dispatch(dispatcher.prepare(message("a")))
    assert len(sender.messages) == 1
    assert "читаемое" in sender.messages[0].text
    assert sender.messages[0].review_task is None


def test_replayed_financial_draft_does_not_offer_a_previously_created_category_task():
    processor, repository, ports = make_flow()
    original = processor.process(message("a")).files[0]
    key = (original.receipt.owner_id, original.receipt.source_key)
    stored = repository.receipts[key]
    repository.receipts[key] = replace(
        stored,
        receipt=replace(stored.receipt, purchase_date=None, review_reasons=("Не удалось прочитать дату покупки",)),
    )
    ports.calls.clear()
    repeated = processor.process(message("a")).files[0]
    assert repeated.status == "draft"
    assert repeated.review_tasks == ()
    assert ports.calls == []


def test_atomic_save_returns_race_winner_without_replacing_manual_data():
    from receipt_bot.application.receipts.stored_receipt import StoredReceipt

    processor, repository, _ports = make_flow()
    first = processor.process(message("a")).files[0]
    new_reference = replace(message("b").attachments[0], source_event_id="new-event")
    new_message = replace(message("b"), event_id="new-event", attachments=(new_reference,))
    winner = StoredReceipt(replace(first.receipt, source_key=new_reference.source_key), ())
    repository.race_winner = winner
    repeated = processor.process(new_message).files[0]
    assert repeated.receipt == winner.receipt
    assert repeated.review_tasks == ()


def test_mixed_pdf_uses_only_usable_text_and_preserves_page_coordinates():
    from receipt_bot.application.messaging.attachment import Attachment
    from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor

    result = ReceiptTextExtractor(MixedPDFReader(), PageOCRRunner()).extract(
        Attachment("receipt.pdf", "application/pdf", b"pdf")
    )
    assert [(line.page_number, line.text, line.box) for line in result.lines] == [
        (1, "Слой", (1, 2, 10, 20)),
        (2, "OCR", (2, 3, 4, 5)),
        (3, "OCR", (2, 3, 4, 5)),
    ]


def test_extraction_rejects_unusable_page_without_image():
    from receipt_bot.application.errors.file_processing_error import FileProcessingError
    from receipt_bot.application.messaging.attachment import Attachment
    from receipt_bot.application.recognition.receipt_text_extractor import ReceiptTextExtractor

    with pytest.raises(FileProcessingError, match="missing_page_image"):
        ReceiptTextExtractor(EmptyPDFReader(), RecognitionPorts()).extract(
            Attachment("a.pdf", "application/pdf", b"pdf")
        )
