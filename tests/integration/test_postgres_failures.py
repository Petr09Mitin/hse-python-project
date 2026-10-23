import os
from uuid import uuid4

import psycopg
import pytest

from receipt_bot.adapters.persistence.connection import connection
from receipt_bot.application.errors.storage_error import StorageError

DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_DSN required")


@pytest.mark.parametrize(
    "query,error_type",
    [
        ("SELECT 'bad'::integer", psycopg.DataError),
        ("SELECT * FROM receipt_bot_missing_table", psycopg.ProgrammingError),
        (
            "CREATE TEMP TABLE repeated (id int PRIMARY KEY); INSERT INTO repeated VALUES (1),(1)",
            psycopg.IntegrityError,
        ),
    ],
)
def test_permanent_database_errors_are_not_retryable(query, error_type):
    with pytest.raises(error_type), connection(DSN, 1, 1000) as database:
        database.execute(query)
    with connection(DSN, 1, 1000) as database:
        assert database.execute("SELECT 1 AS value").fetchone()["value"] == 1


@pytest.mark.parametrize("error_type", [ValueError, TypeError, OverflowError])
def test_programming_error_inside_transaction_is_not_retryable(error_type):
    with pytest.raises(error_type, match="invalid data"), connection(DSN, 1, 1000):
        raise error_type("invalid data")


def test_connection_refusal_and_statement_timeout_remain_retryable():
    with pytest.raises(StorageError) as unavailable, connection("postgresql://127.0.0.1:1/unavailable", 1, 1000):
        pytest.fail("Соединение не должно открыться")
    assert isinstance(unavailable.value.__cause__, psycopg.OperationalError)
    with pytest.raises(StorageError) as timeout, connection(DSN, 1, 20) as database:
        database.execute("SELECT pg_sleep(1)")
    assert isinstance(timeout.value.__cause__, psycopg.errors.QueryCanceled)


def test_lock_timeout_remains_retryable():
    lock_id = uuid4().int % (2**63)
    with psycopg.connect(DSN) as holder:
        holder.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
        with pytest.raises(StorageError) as timeout, connection(DSN, 1, 50) as database:
            database.execute("SET statement_timeout = 1000")
            database.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
        assert isinstance(timeout.value.__cause__, psycopg.errors.LockNotAvailable)
