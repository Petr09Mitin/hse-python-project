from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttachmentReference:
    """Сведения о вложении для скачивания и проверки повторной обработки."""

    source_event_id: str
    file_index: int
    source_token: str = field(repr=False)
    file_name: str
    media_type: str
    size_bytes: int | None = None

    @property
    def source_key(self) -> str:
        return f"{len(self.source_event_id)}:{self.source_event_id}:{self.file_index}"
