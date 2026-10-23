from receipt_bot.adapters.recognition.qwen_client import QwenClient
from receipt_bot.adapters.recognition.qwen_schema import document_text, object_schema, text_model
from receipt_bot.application.errors.file_processing_error import FileProcessingError
from receipt_bot.application.recognition.receipt_classifier import ReceiptClassifier
from receipt_bot.domain.recognition.receipt_decision import ReceiptDecision
from receipt_bot.domain.recognition.recognition_result import RecognitionResult


class QwenReceiptClassifier(ReceiptClassifier):
    """Определяет тип документа отдельным запросом."""

    def __init__(self, client: QwenClient):
        self.client = client

    def classify(self, recognition: RecognitionResult) -> ReceiptDecision:
        schema = object_schema({"is_receipt": {"type": "boolean"}, "reason": {"type": "string"}})
        result = self.client.request(
            "receipt_decision",
            schema,
            "Определи, является ли документ чеком или счётом конкретной покупки для учёта расходов. "
            "Принимай кассовые и товарные чеки, квитанции, ресторанные гостевые счета и пречеки: "
            "is_receipt=true, если документ содержит заказанные товары или услуги, их суммы и итог к оплате. "
            "Гостевой счёт с позициями и итогом подходит даже без отметки об оплате. "
            "Отсутствие ФН, ФД, ФП, QR-кода, ККТ и других фискальных реквизитов не является причиной отказа. "
            "Нечитаемая или краткая дата сама по себе не меняет тип документа; дату проверит следующий этап. "
            "Отклоняй меню, прайс-листы и каталоги без конкретного заказа, рекламу, расписания "
            "и банковские переводы без перечня покупок: is_receipt=false. "
            "Кратко объясни решение по-русски.\nТекст документа:\n" + document_text(recognition),
        )
        try:
            if type(result["is_receipt"]) is not bool:
                raise TypeError("Решение о чеке должно быть логическим значением")
            return ReceiptDecision(result["is_receipt"], text_model(result["reason"]))
        except (ValueError, TypeError) as error:
            raise FileProcessingError("qwen_invalid_receipt_decision") from error
