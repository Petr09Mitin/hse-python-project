import logging
import re

SAFE_CODES = frozenset(
    {
        "application_ready",
        "application_failed",
        "settings_invalid",
        "dependencies_unavailable",
        "storage_prepare_retry",
        "storage_dispatch_retry",
        "dispatch_failed",
        "unfinished_dispatch_failed",
        "telegram_callback_ack_failed",
        "telegram_invalid_message_address",
        "telegram_delivery_failed",
        "telegram_delivery_exhausted",
        "models_ready",
        "models_failed",
    }
)


def safe_record(record: logging.LogRecord) -> bool:
    return (
        record.name.startswith("receipt_bot.")
        and isinstance(record.msg, str)
        and (
            record.msg in SAFE_CODES
            or re.fullmatch(
                r"delivery_(?:permanent_failure|exhausted) "
                r"telegram_(?:[0-9]{3}|http_[0-9]{3}|network_error|callback_too_long)",
                record.msg,
            )
        )
        and not record.args
        and record.exc_info is None
        and record.stack_info is None
    )


def configure_logging() -> None:
    """Выводит только разрешённые коды без адресов и содержимого ответов."""
    handler = logging.StreamHandler()
    handler.addFilter(safe_record)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for name in ("telebot", "openai", "httpx", "httpcore", "urllib3"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
        logger.propagate = True
