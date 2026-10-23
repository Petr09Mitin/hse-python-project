from dataclasses import replace

import pytest

from receipt_bot.application.errors.storage_error import StorageError
from receipt_bot.application.receipts.stored_receipt import StoredReceipt
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from tests.helpers.receipts.receipt_scenarios import make_flow, message


def test_empty_ocr_cannot_produce_a_receipt_or_reach_models(monkeypatch):
    processor, repository, ports = make_flow()
    monkeypatch.setattr(ports, "recognize", lambda *args: RecognitionResult(()))
    result = processor.process(message("a")).files[0]
    assert result.status == "error"
    assert "empty_recognition" in result.explanation
    assert repository.receipts == {}
    assert ports.calls == [("download", "a")]


@pytest.mark.parametrize("mismatch", ["owner", "source", "task_owner", "task_item"])
def test_repository_cannot_return_foreign_receipt_or_tasks_after_save(mismatch):
    processor, repository, _ports = make_flow()
    first = processor.process(message("a")).files[0]
    reference = replace(message("b").attachments[0], source_event_id="new")
    receipt = replace(first.receipt, source_key=reference.source_key)
    tasks = ()
    if mismatch == "owner":
        receipt = replace(receipt, owner_id=2)
    elif mismatch == "source":
        receipt = replace(receipt, source_key="another-source")
    elif mismatch == "task_owner":
        tasks = (replace(first.review_tasks[0], owner_id=2),)
    else:
        tasks = (replace(first.review_tasks[0], item_id="another-item"),)
    repository.race_winner = StoredReceipt(receipt, tasks)
    with pytest.raises(StorageError, match="stored_receipt_mismatch"):
        processor.process(replace(message("b"), attachments=(reference,)))
