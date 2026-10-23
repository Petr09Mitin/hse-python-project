import re
from datetime import date

from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_schema import (
    MONEY_SCHEMA,
    document_text,
    money_model,
    object_schema,
    text_model,
)
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.recognition.receipt_data_structurer import ReceiptDataStructurer
from receipt_bot.domain.recognition.recognition_result import RecognitionResult
from receipt_bot.domain.recognition.structured_item_data import StructuredItemData
from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData


class QwenReceiptDataStructurer(ReceiptDataStructurer):
    """Извлекает неизвестные поля как null, суммы — десятичными строками."""

    def __init__(self, client: QwenClient):
        self.client = client

    def structure(self, recognition: RecognitionResult) -> StructuredReceiptData:
        schema = object_schema(
            {
                "purchase_date": {"type": ["string", "null"], "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                "total": MONEY_SCHEMA,
                "items": {
                    "type": "array",
                    "items": object_schema({"item_name": {"type": ["string", "null"]}, "item_price": MONEY_SCHEMA}),
                },
            }
        )
        text = document_text(recognition)
        result = self.client.request(
            "receipt_data",
            schema,
            "Извлеки дату покупки, итог чека total и все товарные позиции. "
            "Дату покупки ищи в дате чека, покупки, выдачи или строке Открыт; "
            "даты нормативных документов и документов основания не являются датой покупки. "
            "Входная дата может быть ДД.ММ.ГГ, ДД.ММ.ГГГГ или ГГГГ-ММ-ДД, с временем после даты. "
            "Разделители даты: точка, косая черта, дефис или пробел; день и месяц могут быть без ведущего нуля. "
            "Двузначный год ГГ означает 20ГГ (2000–2099); purchase_date верни как YYYY-MM-DD (год-месяц-день). "
            "Не угадывай повреждённые даты: отсутствующий или трёхзначный год означает purchase_date=null. "
            "total возьми из напечатанной строки ИТОГ или ИТОГО, не вычисляй его из товаров. "
            "Все денежные значения total и item_price верни десятичными строками в рублях. "
            "item_price — полная сумма позиции после скидок в рублях, десятичной строкой. "
            "Если указано количество, возьми напечатанную сумму всей позиции, а не цену за единицу. "
            "Перенос названия товара на следующую строку соедини с его названием; "
            "не создавай из продолжения отдельный товар с выдуманной нулевой ценой. "
            "Сохрани каждую отдельную купленную позицию, даже если названия и суммы двух позиций совпадают. "
            "Не включай ИТОГ, оплату и сдачу в товары.\n" + text,
        )
        try:
            raw_date = result["purchase_date"]
            purchase_date = None
            if raw_date is not None:
                if not isinstance(raw_date, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_date) is None:
                    raise ValueError("date")
                purchase_date = date.fromisoformat(raw_date)
                day = f"0?{purchase_date.day}" if purchase_date.day < 10 else str(purchase_date.day)
                month = f"0?{purchase_date.month}" if purchase_date.month < 10 else str(purchase_date.month)
                year = f"{purchase_date.year:04d}"
                if 2000 <= purchase_date.year <= 2099:
                    # Двузначный год всегда означает 20ГГ, без зависимости от текущей даты.
                    year = rf"(?:{year}|{purchase_date.year % 100:02d})"
                separator = r"(?:\s*[./+\-]\s*|\s+)"
                dmy = f"{day}{separator}{month}{separator}{year}"
                ymd = f"{purchase_date.year:04d}{separator}{month}{separator}{day}"
                if re.search(rf"(?<![0-9])(?:{dmy}|{ymd})(?![0-9])", text) is None:
                    purchase_date = None
            if not isinstance(result["items"], list):
                raise TypeError("items")
            items = []
            for item in result["items"]:
                if not isinstance(item, dict) or set(item) != {"item_name", "item_price"}:
                    raise ValueError("item shape")
                name = None if item["item_name"] is None else text_model(item["item_name"])
                items.append(StructuredItemData(name, money_model(item["item_price"])))
            return StructuredReceiptData(purchase_date, money_model(result["total"]), tuple(items))
        except (ValueError, TypeError) as error:
            raise FileProcessingError("qwen_invalid_receipt_data") from error
