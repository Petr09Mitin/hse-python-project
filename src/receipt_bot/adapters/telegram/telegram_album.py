from dataclasses import dataclass, field

from receipt_bot.application.messaging.incoming_message import IncomingMessage


@dataclass
class TelegramAlbum:
    """Короткий буфер исходных событий одного альбома."""

    started_at: float
    updated_at: float
    messages: list[IncomingMessage] = field(default_factory=list)
