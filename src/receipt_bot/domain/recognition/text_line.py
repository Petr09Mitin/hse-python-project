from dataclasses import dataclass


@dataclass(frozen=True)
class TextLine:
    """Распознанный текст строки и её положение в документе."""

    page_number: int
    order: int
    text: str
    box: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "box", tuple(self.box))
