from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryOutcome:
    """Конечный исход доставки после не более трёх попыток адаптера."""

    status: str
    error_code: str | None = None
    attempts: int = 1
