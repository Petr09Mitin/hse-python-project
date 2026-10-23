from dataclasses import dataclass, field

from receipt_bot.domain.recognition.text_line import TextLine


@dataclass(frozen=True)
class DocumentPage:
    """Текст и изображение одной страницы документа."""

    page_number: int
    text_lines: tuple[TextLine, ...]
    width: float
    height: float
    image: bytes | None = field(default=None, repr=False)
    text_usable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "text_lines", tuple(self.text_lines))
