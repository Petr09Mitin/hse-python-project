from dataclasses import dataclass

from receipt_bot.domain.recognition.text_line import TextLine


@dataclass(frozen=True)
class RecognitionResult:
    """Распознанный текст документа, разбитый на строки."""

    lines: tuple[TextLine, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
