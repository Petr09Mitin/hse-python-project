from receipt_bot.application.messaging.incoming_message import IncomingMessage
from receipt_bot.application.messaging.outgoing_message import OutgoingMessage
from receipt_bot.application.receipts.expense_repository import ExpenseRepository
from receipt_bot.application.reports.report_exporter import ReportExporter
from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution
from receipt_bot.application.reports.report_period_resolver import ReportPeriodResolver
from receipt_bot.domain.reports.expense_report import ExpenseReport
from receipt_bot.domain.reports.expense_report_row import ExpenseReportRow
from receipt_bot.domain.reports.report_period import ReportPeriod


class ReportProcessor:
    """Готовит отчёт о расходах владельца за выбранный период."""

    def __init__(self, resolver: ReportPeriodResolver, repository: ExpenseRepository, exporter: ReportExporter):
        self.resolver = resolver
        self.repository = repository
        self.exporter = exporter

    def prepare(self, message: IncomingMessage) -> ReportPeriodResolution:
        return self.resolver.resolve(message)

    def process(self, message: IncomingMessage, resolution: ReportPeriodResolution) -> OutgoingMessage:
        if resolution.kind != "ready":
            return OutgoingMessage(message.chat_id, resolution.text or "Для отчёта используйте /report.")
        report = self._build(message.owner_id, resolution.period)
        if not report.rows:
            return OutgoingMessage(message.chat_id, "За выбранный период нет учтённых расходов.")
        return OutgoingMessage(message.chat_id, "Отчёт за выбранный период готов.", self.exporter.export(report))

    def _build(self, owner_id: int, period: ReportPeriod) -> ExpenseReport:
        rows = []
        receipts = self.repository.list_receipts(owner_id, period)
        for receipt in receipts:
            if receipt.owner_id != owner_id or not receipt.is_reportable:
                continue
            if not period.contains(receipt.purchase_date):
                continue
            for item in receipt.items:
                rows.append(ExpenseReportRow(receipt.purchase_date, item.item_name, item.item_price, item.category))
        rows.sort(key=lambda row: row.purchase_date)
        return ExpenseReport(period, tuple(rows))
