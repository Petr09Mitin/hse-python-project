from dataclasses import replace
from datetime import date

import pytest

from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.money import Money
from receipt_bot.domain.reports.report_period import ReportPeriod
from tests.helpers.messaging.memory_sender import MemorySender
from tests.helpers.receipts.memory_expenses import MemoryExpenses
from tests.helpers.receipts.receipt_scenarios import make_flow, message
from tests.helpers.reports.memory_conversations import MemoryConversations
from tests.helpers.reports.memory_report_exporter import MemoryReportExporter


def incoming(event_id, text, owner_id=1, chat_id=10):
    from receipt_bot.application.messaging.incoming_message import IncomingMessage

    return IncomingMessage(owner_id, chat_id, event_id, text)


def make_reports(repository=None):
    from receipt_bot.application.reports.report_period_resolver import ReportPeriodResolver
    from receipt_bot.application.reports.report_processor import ReportProcessor

    conversations = MemoryConversations()
    resolver = ReportPeriodResolver(conversations)
    exporter = MemoryReportExporter()
    reports = ReportProcessor(resolver, repository or MemoryExpenses(), exporter)
    return reports, conversations, exporter


def test_dates_dialogue_replays_start_even_after_completion_and_new_dialogue():
    from receipt_bot.application.reports.report_period_resolver import ReportPeriodResolver

    reports, conversations, exporter = make_reports()
    assert reports.prepare(incoming("1", "/report")).kind == "question"
    start = reports.prepare(incoming("2", "20.10.2026"))
    assert start.kind == "question"
    ready = reports.prepare(incoming("3", "22.10.2026"))
    assert ready.period == ReportPeriod(date(2026, 10, 20), date(2026, 10, 22))
    restored = ReportPeriodResolver(conversations)
    assert restored.resolve(incoming("2", "20.10.2026")) == start
    restored.resolve(incoming("4", "/report"))
    assert restored.resolve(incoming("3", "22.10.2026")) == ready
    assert conversations.states[(1, 10)].stage == "start"
    assert exporter.reports == []


def test_cancel_replay_does_not_cancel_a_later_dialogue():
    reports, conversations, _exporter = make_reports()
    reports.prepare(incoming("1", "/report"))
    cancelled = reports.prepare(incoming("2", "/cancel"))
    assert cancelled.kind == "cancelled"
    reports.prepare(incoming("3", "/report"))
    assert reports.prepare(incoming("2", "/cancel")) == cancelled
    assert conversations.states[(1, 10)].stage == "start"


@pytest.mark.parametrize("text", ["31.02.2026", "2026-10-22", "2.10.2026", "22.10.26", "words", ""])
def test_invalid_date_keeps_current_question_active(text):
    reports, conversations, _exporter = make_reports()
    reports.prepare(incoming("1", "/report"))
    result = reports.prepare(incoming("2", text))
    assert result.kind == "error"
    assert result.period is None
    assert conversations.states[(1, 10)].stage == "start"
    reports.prepare(incoming("3", "22.10.2026"))
    result = reports.prepare(incoming("4", "21.10.2026"))
    assert result.kind == "error"
    assert conversations.states[(1, 10)].stage == "end"
    assert reports.prepare(incoming("4", "21.10.2026")) == result


def test_dialogue_is_scoped_to_owner_and_chat_and_new_report_replaces_start():
    reports, conversations, _exporter = make_reports()
    reports.prepare(incoming("same", "/report"))
    reports.prepare(incoming("next", "20.10.2026"))
    assert reports.prepare(incoming("same", "21.10.2026", owner_id=2)).kind == "ignored"
    assert reports.prepare(incoming("same", "21.10.2026", chat_id=11)).kind == "ignored"
    reports.prepare(incoming("new", "/report"))
    assert conversations.states[(1, 10)].stage == "start"
    assert conversations.states[(1, 10)].start_date is None


@pytest.mark.parametrize(
    "text", ["/report 31.02.2026 22.10.2026", "/report 22.10.2026", "/report 23.10.2026 22.10.2026"]
)
def test_invalid_report_command_has_no_period(text):
    reports, _conversations, exporter = make_reports()
    assert reports.prepare(incoming("1", text)).kind == "error"
    assert exporter.reports == []


def test_report_uses_purchase_dates_inclusive_and_exact_sums_with_unknown_category():
    from receipt_bot.application.receipts.stored_receipt import StoredReceipt

    processor, repository, _ports = make_flow()
    original = processor.process(message("a")).files[0].receipt
    repository.receipts = {}
    for index, (owner, day, reasons) in enumerate(
        [(1, 19, ()), (1, 20, ()), (1, 22, ()), (1, 23, ()), (2, 21, ()), (1, 21, ("Mismatch",))]
    ):
        receipt = replace(
            original, id=str(index), owner_id=owner, purchase_date=date(2026, 10, day), review_reasons=reasons
        )
        repository.receipts[(owner, str(index))] = StoredReceipt(receipt, ())
    reports, _, exporter = make_reports(repository)
    request = incoming("report", "/report 20.10.2026 22.10.2026")
    reports.process(request, reports.prepare(request))
    report = exporter.reports[0]
    assert [row.purchase_date.day for row in report.rows] == [20, 20, 22, 22]
    assert report.total == Money(60002)
    assert report.category_totals == {DEFAULT_CATEGORIES[0]: Money(20000), None: Money(40002)}


def test_empty_report_returns_explanation_without_export():
    reports, _conversations, exporter = make_reports()
    request = incoming("1", "/report 20.10.2026 22.10.2026")
    response = reports.process(request, reports.prepare(request))
    assert response.chat_id == 10
    assert response.export_file is None
    assert "нет" in response.text.lower()
    assert exporter.reports == []


def test_completed_report_exports_saved_snapshot():
    processor, repository, _ports = make_flow()
    processor.process(message("a"))
    reports, _conversations, exporter = make_reports(repository)
    request = incoming("1", "/report@receiptbot 20.10.2026 20.10.2026")
    response = reports.process(request, reports.prepare(request))
    assert response.export_file.content == b"xlsx"
    assert exporter.reports[0].total == Money(30001)


def make_dispatcher():
    from receipt_bot.application.categories.category_review_processor import CategoryReviewProcessor
    from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher

    processor, repository, ports = make_flow()
    reports, conversations, _exporter = make_reports(repository)
    sender = MemorySender()
    dispatcher = MessageDispatcher(processor, CategoryReviewProcessor(repository), reports, sender)
    return dispatcher, processor, repository, ports, reports, conversations, sender


def test_receipt_and_callback_do_not_become_period_answers():
    from receipt_bot.application.categories.review_choice import ReviewChoice

    dispatcher, _processor, repository, ports, _reports, conversations, sender = make_dispatcher()
    dispatcher.prepare(incoming("report", "/report"))
    prepared = dispatcher.prepare(message("a"))
    assert ports.calls == []
    assert sender.messages == []
    outcomes = dispatcher.dispatch(prepared)
    assert len(outcomes) == 2
    assert sender.messages[0].chat_id == 10
    assert "3.0001" in sender.messages[0].text
    task = sender.messages[1].review_task
    assert task.status == "pending"
    callback = replace(incoming("callback", "20.10.2026"), review_choice=ReviewChoice(task.id, "health"))
    dispatcher.dispatch(dispatcher.prepare(callback))
    assert repository.tasks[task.id].answer_category.code == "health"
    assert conversations.states[(1, 10)].stage == "start"
    assert dispatcher.prepare(incoming("start", "20.10.2026")).resolution.kind == "question"


def test_prepare_persists_order_before_any_heavy_dispatch():
    dispatcher, _processor, _repository, _ports, _reports, conversations, sender = make_dispatcher()
    first = dispatcher.prepare(incoming("1", "/report"))
    second = dispatcher.prepare(incoming("2", "20.10.2026"))
    third = dispatcher.prepare(incoming("3", "22.10.2026"))
    assert third.resolution.period == ReportPeriod(date(2026, 10, 20), date(2026, 10, 22))
    assert sender.messages == []
    dispatcher.dispatch(third)
    dispatcher.dispatch(first)
    dispatcher.dispatch(second)
    assert conversations.states[(1, 10)] is None


def test_terminal_delivery_failure_still_returns_business_completion_to_runner():
    from receipt_bot.application.messaging.delivery_outcome import DeliveryOutcome

    dispatcher, _processor, repository, _ports, _reports, _conversations, sender = make_dispatcher()
    sender.outcome = DeliveryOutcome("permanent_failure", "blocked", 1)
    outcomes = dispatcher.dispatch(dispatcher.prepare(message("a")))
    assert all(outcome.status == "permanent_failure" for outcome in outcomes)
    assert len(repository.receipts) == 1


def test_storage_failure_does_not_send_a_successful_summary():
    from receipt_bot.application.errors.storage_error import StorageError

    dispatcher, _processor, repository, _ports, _reports, _conversations, sender = make_dispatcher()
    repository.fail_storage = True
    with pytest.raises(StorageError):
        dispatcher.dispatch(dispatcher.prepare(message("a")))
    assert sender.messages == []


def test_transport_rejection_explains_resend_without_running_receipt_flow():
    from receipt_bot.application.messaging.incoming_message import IncomingMessage
    from receipt_bot.application.messaging.message_dispatcher import MessageDispatcher
    from tests.helpers.messaging.memory_sender import MemorySender
    from tests.helpers.receipts.receipt_scenarios import make_flow

    processor, _, ports = make_flow()
    sender = MemorySender()
    dispatcher = MessageDispatcher(processor, None, None, sender)
    message = IncomingMessage(
        1, 10, "late", "/receipt", rejection_reason="Альбом завершён: отправьте файл снова с /receipt."
    )
    result = dispatcher.prepare(message)
    dispatcher.dispatch(result)
    assert "снова" in sender.messages[0].text
    assert ports.calls == []
