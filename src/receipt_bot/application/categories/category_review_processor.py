from datetime import UTC, datetime

from receipt_bot.application.categories.review_choice import ReviewChoice
from receipt_bot.application.receipts.expense_repository import ExpenseRepository


class CategoryReviewProcessor:
    """Ручной ответ применяется только к ожидающей задаче её владельца."""

    def __init__(self, repository: ExpenseRepository):
        self.repository = repository

    def process(self, owner_id: int, choice: ReviewChoice) -> str:
        task = self.repository.get_review_task(owner_id, choice.task_id)
        if task is None or task.owner_id != owner_id:
            return "Задача не найдена или недоступна."
        if task.status != "pending":
            return "Выбор уже принят."
        category = None
        for option in task.options:
            if option.code == choice.category_code:
                category = option
                break
        if category is None:
            return "Выберите категорию из предложенных вариантов."
        if self.repository.answer_review(owner_id, task.id, category, datetime.now(UTC)):
            return "Категория сохранена."
        return "Выбор уже принят."
