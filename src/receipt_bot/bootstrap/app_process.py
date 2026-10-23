import logging
import os
import signal

from receipt_bot.adapters.persistence.schema import prepare_schema
from receipt_bot.bootstrap.application_settings import ApplicationSettings
from receipt_bot.bootstrap.build_application import build_application
from receipt_bot.bootstrap.readiness import check_dependencies
from receipt_bot.bootstrap.safe_logging import configure_logging

logger = logging.getLogger("receipt_bot.bootstrap.app_process")


def main() -> int:
    configure_logging()
    try:
        settings = ApplicationSettings()
        prepare_schema(settings.postgres_dsn, settings.connect_timeout, settings.statement_timeout_ms)
        check_dependencies(settings)
        runner = build_application(settings)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda signum, frame: runner.stop())
        logger.info("application_ready")
        runner.run()
    except Exception:  # noqa: BLE001 -- граница процесса скрывает содержимое ответа SDK и возвращает код ошибки.
        logger.error("application_failed")
        return 1
    return 0


if __name__ == "__main__":
    # Обработчики завершены; основной процесс удалит оставшиеся дочерние процессы.
    os._exit(main())
