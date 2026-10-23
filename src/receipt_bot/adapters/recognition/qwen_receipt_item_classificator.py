import json

from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_schema import object_schema
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.recognition.receipt_item_classificator import ReceiptItemClassificator
from receipt_bot.domain.categories.category import Category
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData


class QwenReceiptItemClassificator(ReceiptItemClassificator):
    """Каждая позиция получает собственный запрос с закрытым справочником."""

    def __init__(self, client: QwenClient):
        self.client = client

    def classify_item(self, item: StructuredItemData, categories: tuple[Category, ...]) -> Category | None:
        codes = {category.code: category for category in categories}
        schema = object_schema(
            {"category_code": {"type": ["string", "null"], "enum": [*codes, None]}, "needs_review": {"type": "boolean"}}
        )
        schema["oneOf"] = [
            {"properties": {"category_code": {"enum": list(codes)}, "needs_review": {"const": False}}},
            {"properties": {"category_code": {"type": "null"}, "needs_review": {"const": True}}},
        ]
        prompt = (
            "Выбери категорию только для этой товарной позиции. Еда и напитки относятся к food (Продукты). "
            "Если категория ясна, needs_review=false. Если неоднозначно, category_code=null и needs_review=true.\n"
        )
        prompt += json.dumps(
            {"item_name": item.item_name, "categories": {c.code: c.name for c in categories}}, ensure_ascii=False
        )
        result = self.client.request("item_category", schema, prompt)
        try:
            code = result["category_code"]
            if code is not None and (not isinstance(code, str) or code not in codes):
                raise ValueError("category")
            needs_review = result["needs_review"]
            if type(needs_review) is not bool or needs_review != (code is None):
                raise ValueError("Несогласованный ответ категории")
            return None if code is None else codes[code]
        except (ValueError, TypeError) as error:
            raise FileProcessingError("qwen_invalid_item_category") from error
