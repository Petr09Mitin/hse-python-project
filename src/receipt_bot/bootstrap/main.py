import logging
import sys

from receipt_bot.bootstrap.application_settings import ApplicationSettings
from receipt_bot.bootstrap.safe_logging import configure_logging
from receipt_bot.bootstrap.supervisor import supervise

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    try:
        settings = ApplicationSettings()
    except (ValueError, TypeError):
        logger.error("settings_invalid")
        return 1
    return supervise([sys.executable, "-m", "receipt_bot.bootstrap.app_process"], settings.shutdown_timeout)
