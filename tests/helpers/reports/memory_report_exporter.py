from receipt_bot.application.messaging.attachment import Attachment


class MemoryReportExporter:
    def __init__(self):
        self.reports = []

    def export(self, report):
        self.reports.append(report)
        return Attachment("expenses.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"xlsx")
