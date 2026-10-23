from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewChoice:
    """Ответ на сохранённую задачу; право проверяется по владельцу входа."""

    task_id: str
    category_code: str
