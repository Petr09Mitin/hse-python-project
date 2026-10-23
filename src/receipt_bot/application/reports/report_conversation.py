from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportConversation:
    """Активный вопрос о начале либо конце периода одного владельца и диалога."""

    owner_id: int
    chat_id: int
    stage: str
    start_date: date | None = None
