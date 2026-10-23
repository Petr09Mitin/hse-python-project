from datetime import datetime

from psycopg.types.json import Jsonb

from receipt_bot.adapters.persistence.connection import connection, validate_limits
from receipt_bot.adapters.persistence.serialization import category_data, money_units, receipt_model, task_model
from receipt_bot.application.receipts.expense_repository import ExpenseRepository
from receipt_bot.application.receipts.stored_receipt import StoredReceipt
from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.categories.review_task import ReviewTask
from receipt_bot.domain.receipts.receipt import Receipt
from receipt_bot.domain.reports.report_period import ReportPeriod


class PostgresExpenseRepository(ExpenseRepository):
    """Атомарное хранилище чеков с отдельным соединением на операцию."""

    def __init__(self, dsn: str, connect_timeout: int = 5, statement_timeout_ms: int = 10000):
        validate_limits(connect_timeout, statement_timeout_ms)
        self.dsn = dsn
        self.connect_timeout = connect_timeout
        self.statement_timeout_ms = statement_timeout_ms

    def _connection(self):
        return connection(self.dsn, self.connect_timeout, self.statement_timeout_ms)

    def _load(self, database, row: dict) -> StoredReceipt:
        records = database.execute(
            "SELECT i.*,to_jsonb(t) AS task FROM receipt_items i LEFT JOIN review_tasks t ON t.item_id=i.id "
            "AND t.owner_id=i.owner_id WHERE i.owner_id=%s AND i.receipt_id=%s ORDER BY i.position,t.id",
            (row["owner_id"], row["id"]),
        ).fetchall()
        items, tasks, seen = [], [], set()
        for record in records:
            if record["id"] not in seen:
                items.append(record)
                seen.add(record["id"])
            if record["task"] is not None:
                tasks.append(record["task"])
        return StoredReceipt(receipt_model(row, items), tuple(task_model(task) for task in tasks))

    def find_by_source(self, owner_id: int, source_key: str) -> StoredReceipt | None:
        with self._connection() as database:
            row = database.execute(
                "SELECT * FROM receipts WHERE owner_id=%s AND source_key=%s", (owner_id, source_key)
            ).fetchone()
            return None if row is None else self._load(database, row)

    def save(self, receipt: Receipt, review_tasks: tuple[ReviewTask, ...]) -> StoredReceipt:
        item_ids = {item.id for item in receipt.items}
        if any(task.owner_id != receipt.owner_id or task.item_id not in item_ids for task in review_tasks):
            raise ValueError("Задача не принадлежит чеку")
        with self._connection() as database:
            inserted = database.execute(
                "INSERT INTO receipts VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                (
                    receipt.id,
                    receipt.owner_id,
                    receipt.source_key,
                    receipt.purchase_date,
                    money_units(receipt.total),
                    Jsonb(receipt.review_reasons),
                    receipt.is_reportable,
                ),
            ).fetchone()
            if inserted is not None:
                for position, item in enumerate(receipt.items):
                    database.execute(
                        "INSERT INTO receipt_items VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            item.id,
                            receipt.owner_id,
                            receipt.id,
                            position,
                            item.item_name,
                            money_units(item.item_price),
                            Jsonb(category_data(item.category)),
                            item.created_at,
                            item.updated_at,
                            Jsonb(item.review_reasons),
                        ),
                    )
                for task in review_tasks:
                    database.execute(
                        "INSERT INTO review_tasks VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            task.id,
                            task.owner_id,
                            task.item_id,
                            Jsonb([category_data(c) for c in task.options]),
                            task.status,
                            Jsonb(category_data(task.answer_category)),
                        ),
                    )
            row = database.execute(
                "SELECT * FROM receipts WHERE owner_id=%s AND source_key=%s", (receipt.owner_id, receipt.source_key)
            ).fetchone()
            return self._load(database, row)

    def get_review_task(self, owner_id: int, task_id: str) -> ReviewTask | None:
        with self._connection() as database:
            row = database.execute(
                "SELECT * FROM review_tasks WHERE owner_id=%s AND id=%s", (owner_id, task_id)
            ).fetchone()
            return None if row is None else task_model(row)

    def answer_review(self, owner_id: int, task_id: str, category: Category, answered_at: datetime) -> bool:
        with self._connection() as database:
            row = database.execute(
                "SELECT * FROM review_tasks WHERE owner_id=%s AND id=%s FOR UPDATE", (owner_id, task_id)
            ).fetchone()
            if row is None or row["status"] != "pending":
                return False
            task = task_model(row)
            if category not in task.options:
                return False
            database.execute(
                "UPDATE receipt_items SET category=%s,updated_at=%s WHERE owner_id=%s AND id=%s",
                (Jsonb(category_data(category)), answered_at, owner_id, task.item_id),
            )
            database.execute(
                "UPDATE review_tasks SET status='answered',answer=%s WHERE owner_id=%s AND id=%s",
                (Jsonb(category_data(category)), owner_id, task_id),
            )
            return True

    def list_receipts(self, owner_id: int, period: ReportPeriod) -> tuple[Receipt, ...]:
        with self._connection() as database:
            database.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            rows = database.execute(
                "SELECT * FROM receipts WHERE owner_id=%s AND purchase_date BETWEEN %s AND %s "
                "AND reportable ORDER BY purchase_date,id",
                (owner_id, period.start_date, period.end_date),
            ).fetchall()
            if not rows:
                return ()
            records = database.execute(
                "SELECT * FROM receipt_items WHERE owner_id=%s AND receipt_id=ANY(%s) ORDER BY receipt_id,position",
                (owner_id, [row["id"] for row in rows]),
            ).fetchall()
            items = {}
            for record in records:
                items.setdefault(record["receipt_id"], []).append(record)
            return tuple(receipt_model(row, items.get(row["id"], [])) for row in rows)
