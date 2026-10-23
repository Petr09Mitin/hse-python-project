import logging

from openai import OpenAI

from receipt_bot.adapters.persistence.connection import connection
from receipt_bot.bootstrap.application_settings import ApplicationSettings
from receipt_bot.bootstrap.prepare_models import model_files
from receipt_bot.bootstrap.safe_logging import configure_logging

logger = logging.getLogger("receipt_bot.bootstrap.readiness")


def check_dependencies(settings: ApplicationSettings) -> None:
    """Проверяет модели, схему БД и доступность Qwen."""
    if not settings.use_api_model:
        for model in model_files():
            path = settings.model_dir / model["path"]
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("models_unavailable")
    with connection(settings.postgres_dsn, settings.connect_timeout, settings.statement_timeout_ms) as database:
        row = database.execute(
            "SELECT to_regclass('receipts') AS receipts, to_regclass('report_events') AS events"
        ).fetchone()
        if row["receipts"] is None or row["events"] is None:
            raise RuntimeError("schema_unavailable")
    with OpenAI(
        base_url=settings.qwen_url, api_key=settings.qwen_api_key, timeout=settings.connect_timeout, max_retries=0
    ) as client:
        if settings.qwen_model not in {model.id for model in client.models.list()}:
            raise RuntimeError("qwen_model_unavailable")


def main() -> int:
    configure_logging()
    try:
        check_dependencies(ApplicationSettings())
    except Exception:  # noqa: BLE001 -- граница процесса скрывает содержимое ответа SDK и возвращает код ошибки.
        logger.error("dependencies_unavailable")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
