from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from receipt_bot.application.errors.storage_error import StorageError


def validate_limits(connect_timeout: int, statement_timeout_ms: int) -> None:
    for value in (connect_timeout, statement_timeout_ms):
        if type(value) is not int or value <= 0:
            raise ValueError("Таймаут БД должен быть положительным целым числом")


@contextmanager
def connection(dsn: str, connect_timeout: int, statement_timeout_ms: int):
    validate_limits(connect_timeout, statement_timeout_ms)
    try:
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout,
            options=f"-c statement_timeout={statement_timeout_ms} -c lock_timeout={statement_timeout_ms}",
            row_factory=dict_row,
        ) as database:
            yield database
    except (psycopg.OperationalError, psycopg.InterfaceError) as error:
        raise StorageError("storage_operation_failed") from error
