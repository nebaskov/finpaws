from __future__ import annotations

from app.services.categorizer import categorize


def test_russian_keywords() -> None:
    assert categorize("Яндекс Такси").value == "transport"
    assert categorize("Оплата в аптеке").value == "health"
    assert categorize("Подписка на кино").value == "entertainment"


def test_shopping_keywords() -> None:
    assert categorize("Покупка на Ozon").value == "shopping"
    assert categorize("Заказ на вайлдберриз").value == "shopping"


def test_unknown_to_other() -> None:
    assert categorize("непонятная транзакция").value == "other"
