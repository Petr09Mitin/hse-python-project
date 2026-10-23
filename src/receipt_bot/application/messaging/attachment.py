from dataclasses import dataclass, field


@dataclass(frozen=True)
class Attachment:
    """Файл для распознавания или отправки пользователю."""

    file_name: str
    media_type: str
    content: bytes = field(repr=False)
