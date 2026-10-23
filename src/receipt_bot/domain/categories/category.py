from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """Категория со стабильным кодом и названием."""

    code: str
    name: str


DEFAULT_CATEGORIES = (
    Category("food", "Продукты"),
    Category("transport", "Транспорт"),
    Category("household", "Дом и быт"),
    Category("health", "Здоровье"),
    Category("clothing", "Одежда"),
    Category("entertainment", "Развлечения"),
    Category("services", "Услуги"),
    Category("other", "Прочее"),
)
