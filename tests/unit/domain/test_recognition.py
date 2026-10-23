from receipt_bot.domain.money import Money


def test_recognition_keeps_page_line_order_and_coordinates_without_list_aliasing():
    from receipt_bot.domain.recognition.recognition_result import RecognitionResult
    from receipt_bot.domain.recognition.text_line import TextLine

    lines = [TextLine(1, 0, "Молоко", (1, 2, 10, 20)), TextLine(2, 0, "ИТОГ", (2.5, 3, 9, 12))]
    result = RecognitionResult(lines)
    lines.clear()
    assert [(line.page_number, line.order, line.text, line.box) for line in result.lines] == [
        (1, 0, "Молоко", (1, 2, 10, 20)),
        (2, 0, "ИТОГ", (2.5, 3, 9, 12)),
    ]


def test_structured_data_keeps_unknowns_and_exact_zero_without_guessing():
    from receipt_bot.domain.recognition.structured_item_data import StructuredItemData
    from receipt_bot.domain.recognition.structured_receipt_data import StructuredReceiptData

    items = [StructuredItemData(None, None), StructuredItemData("Подарок", Money(0))]
    data = StructuredReceiptData(None, None, items)
    items.clear()
    assert data.purchase_date is None
    assert data.total is None
    assert [(item.item_name, item.item_price) for item in data.items] == [(None, None), ("Подарок", Money(0))]
