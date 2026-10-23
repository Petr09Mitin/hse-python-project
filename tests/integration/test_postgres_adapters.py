import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.reports.report_period_resolver import ReportPeriodResolver
from receipt_bot.domain.categories.category import DEFAULT_CATEGORIES
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.money import Money
from receipt_bot.domain.receipts.receipt import Receipt
from receipt_bot.domain.receipts.receipt_item import ReceiptItem
from receipt_bot.domain.reports.report_period import ReportPeriod

DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN is required for real PostgreSQL tests")


@pytest.fixture
def repositories():
    from receipt_bot.adapters.persistence.postgres_conversation_repository import PostgresConversationRepository
    from receipt_bot.adapters.persistence.postgres_expense_repository import PostgresExpenseRepository
    from receipt_bot.adapters.persistence.schema import prepare_schema

    prepare_schema(DSN)
    return PostgresExpenseRepository(DSN), PostgresConversationRepository(DSN)


def sample(owner=10):
    now = datetime.now(UTC)
    item = ReceiptItem(str(uuid4()), "Молоко", Money(123456), None, now, now)
    receipt = Receipt(str(uuid4()), owner, str(uuid4()), date(2026, 10, 1), Money(123456), (item,))
    task = ReviewTask(str(uuid4()), owner, item.id, DEFAULT_CATEGORIES)
    return receipt, task


def test_save_returns_existing_receipt_preserving_manual_category(repositories):
    expenses, _ = repositories
    receipt, task = sample()
    expenses.save(receipt, (task,))
    assert expenses.answer_review(10, task.id, DEFAULT_CATEGORIES[1], datetime.now(UTC))
    conflicting = replace(receipt, id=str(uuid4()))
    stored = expenses.save(conflicting, ())
    assert stored.receipt.id == receipt.id
    assert stored.receipt.items[0].category == DEFAULT_CATEGORIES[1]
    assert stored.review_tasks[0].status == "answered"
    assert expenses.find_by_source(11, receipt.source_key) is None
    assert expenses.get_review_task(11, task.id) is None


def test_save_race_and_review_race_have_one_winner(repositories):
    expenses, _ = repositories
    receipt, task = sample()
    with ThreadPoolExecutor(2) as workers:
        saved = list(workers.map(lambda _: expenses.save(receipt, (task,)), range(2)))
        answers = list(
            workers.map(lambda c: expenses.answer_review(10, task.id, c, datetime.now(UTC)), DEFAULT_CATEGORIES[:2])
        )
    assert saved[0] == saved[1]
    assert sorted(answers) == [False, True]
    assert not expenses.answer_review(11, task.id, DEFAULT_CATEGORIES[0], datetime.now(UTC))


def test_bad_task_rolls_back_whole_receipt(repositories):
    expenses, _ = repositories
    receipt, task = sample()
    invalid = replace(task, item_id="not_in_receipt")
    with pytest.raises(ValueError):
        expenses.save(receipt, (invalid,))
    assert expenses.find_by_source(10, receipt.source_key) is None


def test_report_dates_are_inclusive_and_drafts_are_excluded(repositories):
    expenses, _ = repositories
    owner = int(uuid4().int % 10**12) + 100
    receipt, task = sample(owner)
    expenses.save(receipt, (task,))
    expenses.save(
        replace(
            receipt,
            id=str(uuid4()),
            source_key=str(uuid4()),
            total=None,
            items=(replace(receipt.items[0], id=str(uuid4())),),
        ),
        (),
    )
    period = ReportPeriod(date(2026, 10, 1), date(2026, 10, 1))
    assert [r.id for r in expenses.list_receipts(owner, period)] == [receipt.id]
    assert expenses.list_receipts(owner + 1, period) == ()


def test_report_reads_receipts_and_items_in_two_queries_regardless_of_receipt_count(repositories, monkeypatch):
    import psycopg

    expenses, _ = repositories
    owner = int(uuid4().int % 10**12) + 100
    period = ReportPeriod(date(2026, 10, 1), date(2026, 10, 1))
    original_execute = psycopg.Connection.execute
    reads = []

    def record_read(database, query, *args, **kwargs):
        if query.lstrip().upper().startswith("SELECT"):
            reads.append(query)
        return original_execute(database, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", record_read)
    counts = []
    for count in (1, 3):
        for _ in range(count - (0 if count == 1 else 1)):
            receipt, task = sample(owner)
            expenses.save(receipt, (task,))
        reads.clear()
        result = expenses.list_receipts(owner, period)
        assert len(result) == count
        counts.append(len(reads))
    assert counts == [2, 2]
    assert all("review_tasks" not in query for query in reads)


def test_conversation_event_survives_completion_and_cancel(repositories):
    _, conversations = repositories
    resolver = ReportPeriodResolver(conversations)
    owner = int(uuid4().int % 10**12) + 100
    start = IncomingMessage(owner, 77, "start", "/report")
    first = IncomingMessage(owner, 77, "first", "01.10.2026")
    last = IncomingMessage(owner, 77, "last", "22.10.2026")
    resolver.resolve(start)
    original = resolver.resolve(first)
    assert resolver.resolve(last).kind == "ready"
    assert resolver.resolve(first) == original
    resolver.resolve(IncomingMessage(owner, 77, "cancel", "/cancel"))
    assert resolver.resolve(first) == original
    assert resolver.resolve(IncomingMessage(owner + 1, 77, "first", "01.10.2026")).kind == "ignored"


def test_conversation_race_calls_pure_change_once_and_rollback(repositories):
    from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution

    _, conversations = repositories
    owner = int(uuid4().int % 10**12) + 100
    calls = []

    def change(state):
        calls.append(state)
        return None, ReportPeriodResolution("cancelled", "Отмена")

    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(lambda _: conversations.transition(owner, 1, "same", change), range(2)))
    assert len(calls) == 1
    assert results[0] == results[1]

    def broken(state):
        raise ValueError("broken transition")

    with pytest.raises(ValueError, match="broken transition"):
        conversations.transition(owner, 1, "rollback", broken)
    assert conversations.transition(owner, 1, "rollback", change).kind == "cancelled"


def test_database_numeric_precision_and_overflow_rollback(repositories):
    expenses, _ = repositories
    receipt, _ = sample()
    amount = Money(10**38 - 1)
    receipt = replace(receipt, total=amount, items=(replace(receipt.items[0], item_price=amount),))
    assert expenses.save(receipt, ()).receipt.total == amount
    overflow = replace(receipt, id=str(uuid4()), source_key=str(uuid4()), total=Money(10**38))
    with pytest.raises(ValueError, match="точность хранилища"):
        expenses.save(overflow, ())
    assert expenses.find_by_source(10, overflow.source_key) is None


def test_report_uses_one_snapshot_during_sequential_category_updates(repositories, monkeypatch):
    from threading import Event

    import psycopg

    expenses, _ = repositories
    owner = int(uuid4().int % 10**12) + 100
    samples = sorted((sample(owner), sample(owner)), key=lambda pair: pair[0].id)
    for receipt, task in samples:
        expenses.save(receipt, (task,))
    first_read, updates_finished = Event(), Event()
    original_execute = psycopg.Connection.execute

    def execute_and_pause_after_receipts(database, query, *args, **kwargs):
        result = original_execute(database, query, *args, **kwargs)
        if query.startswith("SELECT * FROM receipts WHERE owner_id="):
            first_read.set()
            assert updates_finished.wait(5), "Изменение категорий не завершилось"
        return result

    def answer_both_tasks_in_order():
        assert first_read.wait(5), "Отчёт не прочитал чеки"
        try:
            for _, task in samples:
                assert expenses.answer_review(owner, task.id, DEFAULT_CATEGORIES[0], datetime.now(UTC))
        finally:
            updates_finished.set()

    monkeypatch.setattr(psycopg.Connection, "execute", execute_and_pause_after_receipts)
    with ThreadPoolExecutor(1) as workers:
        update_future = workers.submit(answer_both_tasks_in_order)
        receipts = expenses.list_receipts(owner, ReportPeriod(date(2026, 10, 1), date(2026, 10, 1)))
        update_future.result(timeout=5)
    assert [receipt.items[0].category for receipt in receipts] == [None, None]
    assert expenses.get_review_task(owner, samples[1][1].id).status == "answered"
