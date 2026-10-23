from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptDecision:
    """Решение о типе документа с объяснением."""

    is_receipt: bool
    reason: str
