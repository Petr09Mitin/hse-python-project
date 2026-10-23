import re

from receipt_bot.domain.money import Money
from receipt_bot.domain.recognition.recognition_result import RecognitionResult

MONEY_SCHEMA = {"type": ["string", "null"], "pattern": r"^[0-9]+(?:\.[0-9]{1,4})?$"}


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def document_text(recognition: RecognitionResult) -> str:
    return "\n".join(line.text for line in recognition.lines)


def text_model(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Ожидается текст")
    if not value.strip():
        raise ValueError("Пустой текст")
    if "\x00" in value:
        raise ValueError("Текст содержит NUL")
    value.encode("utf-8")
    return value


def money_model(value: str | None) -> Money | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 42 or re.fullmatch(r"[0-9]+(?:\.[0-9]{1,4})?", value) is None:
        raise ValueError("Неверная десятичная сумма")
    whole, _, fractional = value.partition(".")
    units = int(whole) * 10000 + int(fractional.ljust(4, "0"))
    if units >= 10**38:
        raise ValueError("Сумма превышает точность хранилища NUMERIC(38,0)")
    return Money(units)
