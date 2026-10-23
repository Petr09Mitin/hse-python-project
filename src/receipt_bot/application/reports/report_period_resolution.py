from dataclasses import dataclass

from receipt_bot.domain.reports.report_period import ReportPeriod


@dataclass(frozen=True)
class ReportPeriodResolution:
    """Сохраняемый результат события, в том числе завершённого или отменённого."""

    kind: str
    text: str = ""
    period: ReportPeriod | None = None
