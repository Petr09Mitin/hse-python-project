from dataclasses import dataclass

from receipt_bot.application.categories.review_choice import ReviewChoice
from receipt_bot.application.messaging.attachment_reference import AttachmentReference


@dataclass(frozen=True)
class IncomingMessage:
    """Один вход с идентификаторами всех подтверждаемых исходных событий."""

    owner_id: int
    chat_id: int
    event_id: str
    text: str = ""
    attachments: tuple[AttachmentReference, ...] = ()
    review_choice: ReviewChoice | None = None
    command: str | None = None
    acknowledgement_ids: tuple[str, ...] = ()
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        command = self.command
        if command is None:
            for word in self.text.split():
                if word.startswith("/"):
                    command = word.split("@", 1)[0]
                    break
        if command is not None:
            command = command.split("@", 1)[0]
        object.__setattr__(self, "attachments", tuple(self.attachments))
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "acknowledgement_ids", tuple(self.acknowledgement_ids) or (self.event_id,))
