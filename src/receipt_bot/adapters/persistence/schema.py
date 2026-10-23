from pathlib import Path

from receipt_bot.adapters.persistence.connection import connection


def prepare_schema(dsn: str, connect_timeout: int = 5, statement_timeout_ms: int = 10000) -> None:
    """Готовит схему до начала приёма сообщений."""
    with connection(dsn, connect_timeout, statement_timeout_ms) as database:
        database.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
