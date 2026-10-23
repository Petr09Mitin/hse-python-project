from dataclasses import dataclass

from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution


@dataclass(frozen=True)
class PreparedMessage:
    """Запрос с выбранным обработчиком и данными для его выполнения."""

    message: IncomingMessage
    route: str
    resolution: ReportPeriodResolution | None = None
