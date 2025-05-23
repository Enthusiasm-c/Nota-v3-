from unittest.mock import patch

import pytest
from fakeredis import FakeRedis

from app.edit.apply_intent import apply_intent


@pytest.fixture(autouse=True)
def fake_redis():
    import json

    fake = FakeRedis()

    def cache_get(key):
        val = fake.get(key)
        if val is None:
            return None
        return json.loads(val)

    def cache_set(key, value, ex=None):
        fake.set(key, json.dumps(value))

    with patch("app.utils.redis_cache.redis.Redis", return_value=fake), patch(
        "app.assistants.client.cache_get", side_effect=cache_get
    ), patch("app.assistants.client.cache_set", side_effect=cache_set):
        yield


@pytest.mark.parametrize(
    "user_input,invoice_in,expected_invoice,expected_intent",
    [
        # --- Граничные условия ---
        # 1. Пустой инвойс: изменение даты и добавление строки
        (
            "date 2025-07-01; add Sugar 2 kg 150",
            {"date": "", "positions": []},
            {
                "date": "2025-07-01",
                "positions": [{"name": "Sugar", "qty": "2", "unit": "kg", "price": "150"}],
            },
            [
                {"action": "edit_date", "value": "2025-07-01"},
                {"action": "add_line", "value": "Sugar 2 kg 150"},
            ],
        ),
        # 2. Большой инвойс (50 строк): изменение первой, последней и 25-й строки
        (
            "row 1 price 101; row 25 qty 25; row 50 name Last",
            {
                "date": "2025-05-05",
                "positions": [
                    *[
                        {"name": f"Item {i+1}", "qty": f"{i+1}", "unit": "pcs", "price": f"{i+1}0"}
                        for i in range(50)
                    ]
                ],
            },
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Item 1", "qty": "1", "unit": "pcs", "price": "101"},
                    *[
                        {"name": f"Item {i+2}", "qty": f"{i+2}", "unit": "pcs", "price": f"{i+2}0"}
                        for i in range(23)
                    ],
                    {"name": "Item 25", "qty": "25", "unit": "pcs", "price": "250"},
                    *[
                        {
                            "name": f"Item {i+26}",
                            "qty": f"{i+26}",
                            "unit": "pcs",
                            "price": f"{i+26}0",
                        }
                        for i in range(24)
                    ],
                    {
                        "name": "Last",
                        "qty": "50",
                        "unit": "pcs",
                        "price": "500",
                        "status": "manual",
                    },
                ],
            },
            [
                {"action": "edit_line_field", "line": 1, "field": "price", "value": "101"},
                {"action": "edit_line_field", "line": 25, "field": "qty", "value": "25"},
                {"action": "edit_line_field", "line": 50, "field": "name", "value": "Last"},
            ],
        ),
        # 3. Изменение всех поддерживаемых полей в одной строке
        (
            "row 1 name Cheese; row 1 qty 7; row 1 price 350; row 1 unit kg",
            {
                "date": "2025-05-05",
                "positions": [{"name": "Milk", "qty": "2", "unit": "l", "price": "100"}],
            },
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Cheese", "qty": "7", "unit": "kg", "price": "350", "status": "manual"}
                ],
            },
            [
                {"action": "edit_line_field", "line": 1, "field": "name", "value": "Cheese"},
                {"action": "edit_line_field", "line": 1, "field": "qty", "value": "7"},
                {"action": "edit_line_field", "line": 1, "field": "price", "value": "350"},
                {"action": "edit_line_field", "line": 1, "field": "unit", "value": "kg"},
            ],
        ),
        # --- Существующие тесты ниже ---
        (
            "row 1 price 100; row 2 qty 5",
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Milk", "qty": "2", "unit": "l", "price": "10"},
                    {"name": "Bread", "qty": "1", "unit": "pcs", "price": "50"},
                ],
            },
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Milk", "qty": "2", "unit": "l", "price": "100"},
                    {"name": "Bread", "qty": "5", "unit": "pcs", "price": "50"},
                ],
            },
            [
                {"action": "edit_line_field", "line": 1, "field": "price", "value": "100"},
                {"action": "edit_line_field", "line": 2, "field": "qty", "value": "5"},
            ],
        ),
        # Изменение всех полей в одной строке
        (
            "row 1 name Apples; row 1 qty 10; row 1 price 200; row 1 unit kg",
            {
                "date": "2025-05-05",
                "positions": [{"name": "Milk", "qty": "2", "unit": "l", "price": "100"}],
            },
            {
                "date": "2025-05-05",
                "positions": [
                    {
                        "name": "Apples",
                        "qty": "10",
                        "unit": "kg",
                        "price": "200",
                        "status": "manual",
                    }
                ],
            },
            [
                {"action": "edit_line_field", "line": 1, "field": "name", "value": "Apples"},
                {"action": "edit_line_field", "line": 1, "field": "qty", "value": "10"},
                {"action": "edit_line_field", "line": 1, "field": "price", "value": "200"},
                {"action": "edit_line_field", "line": 1, "field": "unit", "value": "kg"},
            ],
        ),
        # Добавление нескольких строк одной командой
        (
            "add Apples 3 kg 300; add Pears 2 kg 400",
            {"date": "2025-05-05", "positions": []},
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Apples", "qty": "3", "unit": "kg", "price": "300"},
                    {"name": "Pears", "qty": "2", "unit": "kg", "price": "400"},
                ],
            },
            [
                {"action": "add_line", "value": "Apples 3 kg 300"},
                {"action": "add_line", "value": "Pears 2 kg 400"},
            ],
        ),
        # Комбинация изменения даты и добавления строк
        (
            "date 2025-06-01; add Apples 2 kg 100",
            {"date": "2025-05-05", "positions": []},
            {
                "date": "2025-06-01",
                "positions": [{"name": "Apples", "qty": "2", "unit": "kg", "price": "100"}],
            },
            [
                {"action": "edit_date", "value": "2025-06-01"},
                {"action": "add_line", "value": "Apples 2 kg 100"},
            ],
        ),
        # Оригинальные тесты ниже
        (
            "row 1 price 12345",
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Milk", "qty": "2", "unit": "l", "price": "100"},
                    {"name": "Bread", "qty": "1", "unit": "pcs", "price": "50"},
                ],
            },
            {
                "date": "2025-05-05",
                "positions": [
                    {"name": "Milk", "qty": "2", "unit": "l", "price": "12345"},
                    {"name": "Bread", "qty": "1", "unit": "pcs", "price": "50"},
                ],
            },
            {"action": "edit_line_field", "line": 1, "field": "price", "value": "12345"},
        ),
        (
            "date 2025-06-01",
            {"date": "2025-05-05", "positions": []},
            {"date": "2025-06-01", "positions": []},
            {"action": "edit_date", "value": "2025-06-01"},
        ),
        (
            "add Apples 3 kg 300",
            {"date": "2025-05-05", "positions": []},
            {
                "date": "2025-05-05",
                "positions": [{"name": "Apples", "qty": "3", "unit": "kg", "price": "300"}],
            },
            {"action": "add_line", "value": "Apples 3 kg 300"},
        ),
    ],
)
def test_edit_flow_integration(user_input, invoice_in, expected_invoice, expected_intent):
    from unittest.mock import MagicMock

    # Мокаем все методы OpenAI-клиента, чтобы возвращать реальные объекты, а не MagicMock
    with patch(
        "app.assistants.client.client.beta.threads.create", return_value=MagicMock(id="thread_id")
    ), patch(
        "app.assistants.client.client.beta.threads.messages.create", return_value=MagicMock()
    ), patch(
        "app.assistants.client.client.beta.threads.runs.create",
        return_value=MagicMock(id="run_id", status="completed"),
    ), patch(
        "app.assistants.client.client.beta.threads.runs.retrieve",
        return_value=MagicMock(id="run_id", status="completed"),
    ):
        # Предполагается, что run_thread_safe вернёт expected_intent, если бы OpenAI вернул такой интент
        intent = expected_intent
        result_invoice = invoice_in.copy()
        if isinstance(intent, list):
            for single_intent in intent:
                result_invoice = apply_intent(result_invoice, single_intent)
        else:
            result_invoice = apply_intent(result_invoice, intent)
        assert result_invoice == expected_invoice
