from collections.abc import Callable
from datetime import date

from psycopg.types.json import Jsonb

from receipt_bot.adapters.persistence.connection import connection, validate_limits
from receipt_bot.application.reports.conversation_repository import ConversationRepository
from receipt_bot.application.reports.report_conversation import ReportConversation
from receipt_bot.application.reports.report_period_resolution import ReportPeriodResolution
from receipt_bot.domain.reports.report_period import ReportPeriod


class PostgresConversationRepository(ConversationRepository):
    """Хранит диалоги выбора периода и ответы на обработанные события."""

    def __init__(self, dsn: str, connect_timeout: int = 5, statement_timeout_ms: int = 10000):
        validate_limits(connect_timeout, statement_timeout_ms)
        self.dsn = dsn
        self.connect_timeout = connect_timeout
        self.statement_timeout_ms = statement_timeout_ms

    def transition(
        self,
        owner_id: int,
        chat_id: int,
        event_id: str,
        change: Callable[[ReportConversation | None], tuple[ReportConversation | None, ReportPeriodResolution]],
    ) -> ReportPeriodResolution:
        with connection(self.dsn, self.connect_timeout, self.statement_timeout_ms) as database:
            database.execute(
                "INSERT INTO report_conversations VALUES (%s,%s,NULL) ON CONFLICT DO NOTHING", (owner_id, chat_id)
            )
            row = database.execute(
                "SELECT state FROM report_conversations WHERE owner_id=%s AND chat_id=%s FOR UPDATE",
                (owner_id, chat_id),
            ).fetchone()
            previous = database.execute(
                "SELECT result FROM report_events WHERE owner_id=%s AND chat_id=%s AND event_id=%s",
                (owner_id, chat_id, event_id),
            ).fetchone()
            if previous is not None:
                return self._resolution(previous["result"])
            state = row["state"]
            conversation = (
                None
                if state is None
                else ReportConversation(
                    owner_id,
                    chat_id,
                    state["stage"],
                    None if state["start_date"] is None else date.fromisoformat(state["start_date"]),
                )
            )
            next_state, result = change(conversation)
            if next_state is not None and (next_state.owner_id != owner_id or next_state.chat_id != chat_id):
                raise ValueError("Диалог принадлежит другому владельцу")
            state_data = (
                None
                if next_state is None
                else {
                    "stage": next_state.stage,
                    "start_date": None if next_state.start_date is None else next_state.start_date.isoformat(),
                }
            )
            period = result.period
            result_data = {
                "kind": result.kind,
                "text": result.text,
                "period": None if period is None else [period.start_date.isoformat(), period.end_date.isoformat()],
            }
            database.execute(
                "UPDATE report_conversations SET state=%s WHERE owner_id=%s AND chat_id=%s",
                (Jsonb(state_data), owner_id, chat_id),
            )
            database.execute(
                "INSERT INTO report_events VALUES (%s,%s,%s,%s)", (owner_id, chat_id, event_id, Jsonb(result_data))
            )
            return result

    def _resolution(self, value: dict) -> ReportPeriodResolution:
        period = value["period"]
        return ReportPeriodResolution(
            value["kind"],
            value["text"],
            None if period is None else ReportPeriod(date.fromisoformat(period[0]), date.fromisoformat(period[1])),
        )
