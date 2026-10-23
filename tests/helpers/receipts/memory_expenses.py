from dataclasses import replace


class MemoryExpenses:
    def __init__(self):
        self.receipts = {}
        self.tasks = {}
        self.fail_storage = False
        self.race_winner = None

    def find_by_source(self, owner_id, source_key):
        from receipt_bot.application.errors.storage_error import StorageError

        if self.fail_storage:
            raise StorageError("unavailable")
        return self.receipts.get((owner_id, source_key))

    def save(self, receipt, review_tasks):
        from receipt_bot.application.receipts.stored_receipt import StoredReceipt

        if self.race_winner is not None:
            return self.race_winner
        stored = self.receipts.setdefault((receipt.owner_id, receipt.source_key), StoredReceipt(receipt, review_tasks))
        for task in stored.review_tasks:
            self.tasks[task.id] = task
        return stored

    def get_review_task(self, owner_id, task_id):
        task = self.tasks.get(task_id)
        if task is None or task.owner_id != owner_id:
            return None
        return task

    def answer_review(self, owner_id, task_id, category, answered_at):
        task = self.get_review_task(owner_id, task_id)
        if task is None or task.status != "pending" or category not in task.options:
            return False
        answered = replace(task, status="answered", answer_category=category)
        for key, stored in self.receipts.items():
            if stored.receipt.owner_id != owner_id:
                continue
            items = []
            for item in stored.receipt.items:
                if item.id == task.item_id:
                    item = replace(item, category=category, updated_at=answered_at)
                items.append(item)
            tasks = tuple(answered if old.id == task_id else old for old in stored.review_tasks)
            self.receipts[key] = replace(
                stored, receipt=replace(stored.receipt, items=tuple(items)), review_tasks=tasks
            )
        self.tasks[task_id] = answered
        return True

    def list_receipts(self, owner_id, period):
        return tuple(stored.receipt for stored in self.receipts.values() if stored.receipt.owner_id == owner_id)
