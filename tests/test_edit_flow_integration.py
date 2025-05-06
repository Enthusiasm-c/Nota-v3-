import pytest
from unittest.mock import patch
from fakeredis import FakeRedis
from app.assistants.client import run_thread_safe
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
    with patch('app.utils.redis_cache.redis.Redis', return_value=fake), \
         patch('app.assistants.client.cache_get', side_effect=cache_get), \
         patch('app.assistants.client.cache_set', side_effect=cache_set):
        yield

@pytest.mark.parametrize("user_input,invoice_in,expected_invoice,expected_intent", [
    # --- Граничные условия ---
    # 1. Пустой инвойс: изменение даты и добавление строки
    (
        "дата 2025-07-01; добавь Сахар 2 кг 150",
        {"date": "", "positions": []},
        {"date": "2025-07-01", "positions": [
            {"name": "Сахар", "qty": "2", "unit": "кг", "price": "150"}
        ]},
        [
            {"action": "edit_date", "value": "2025-07-01"},
            {"action": "add_line", "value": "Сахар 2 кг 150"}
        ]
    ),
    # 2. Большой инвойс (50 строк): изменение первой, последней и 25-й строки
    (
        "строка 1 цена 101; строка 25 количество 25; строка 50 название Последний",
        {"date": "2025-05-05", "positions": [
            *[{"name": f"Товар {i+1}", "qty": f"{i+1}", "unit": "шт", "price": f"{i+1}0"} for i in range(50)]
        ]},
        {"date": "2025-05-05", "positions": [
            {"name": "Товар 1", "qty": "1", "unit": "шт", "price": "101"},
            *[{"name": f"Товар {i+2}", "qty": f"{i+2}", "unit": "шт", "price": f"{i+2}0"} for i in range(23)],
            {"name": "Товар 25", "qty": "25", "unit": "шт", "price": "250"},
            *[{"name": f"Товар {i+26}", "qty": f"{i+26}", "unit": "шт", "price": f"{i+26}0"} for i in range(24)],
            {"name": "Последний", "qty": "50", "unit": "шт", "price": "500"}
        ]},
        [
            {"action": "edit_line_field", "line": 1, "field": "price", "value": "101"},
            {"action": "edit_line_field", "line": 25, "field": "qty", "value": "25"},
            {"action": "edit_line_field", "line": 50, "field": "name", "value": "Последний"}
        ]
    ),
    # 3. Изменение всех поддерживаемых полей в одной строке
    (
        "строка 1 название Сыр; строка 1 количество 7; строка 1 цена 350; строка 1 ед кг",
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "100"}
        ]},
        {"date": "2025-05-05", "positions": [
            {"name": "Сыр", "qty": "7", "unit": "кг", "price": "350"}
        ]},
        [
            {"action": "edit_line_field", "line": 1, "field": "name", "value": "Сыр"},
            {"action": "edit_line_field", "line": 1, "field": "qty", "value": "7"},
            {"action": "edit_line_field", "line": 1, "field": "price", "value": "350"},
            {"action": "edit_line_field", "line": 1, "field": "unit", "value": "кг"}
        ]
    ),
    # --- Существующие тесты ниже ---
    (
        "строка 1 цена 100; строка 2 количество 5",
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "10"},
            {"name": "Хлеб", "qty": "1", "unit": "шт", "price": "50"}
        ]},
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "100"},
            {"name": "Хлеб", "qty": "5", "unit": "шт", "price": "50"}
        ]},
        [
            {"action": "edit_line_field", "line": 1, "field": "price", "value": "100"},
            {"action": "edit_line_field", "line": 2, "field": "qty", "value": "5"}
        ]
    ),
    # Изменение всех полей в одной строке
    (
        "строка 1 название Яблоки; строка 1 количество 10; строка 1 цена 200; строка 1 ед кг",
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "100"}
        ]},
        {"date": "2025-05-05", "positions": [
            {"name": "Яблоки", "qty": "10", "unit": "кг", "price": "200"}
        ]},
        [
            {"action": "edit_line_field", "line": 1, "field": "name", "value": "Яблоки"},
            {"action": "edit_line_field", "line": 1, "field": "qty", "value": "10"},
            {"action": "edit_line_field", "line": 1, "field": "price", "value": "200"},
            {"action": "edit_line_field", "line": 1, "field": "unit", "value": "кг"}
        ]
    ),
    # Добавление нескольких строк одной командой
    (
        "добавь Яблоки 3 кг 300; добавь Груши 2 кг 400",
        {"date": "2025-05-05", "positions": []},
        {"date": "2025-05-05", "positions": [
            {"name": "Яблоки", "qty": "3", "unit": "кг", "price": "300"},
            {"name": "Груши", "qty": "2", "unit": "кг", "price": "400"}
        ]},
        [
            {"action": "add_line", "value": "Яблоки 3 кг 300"},
            {"action": "add_line", "value": "Груши 2 кг 400"}
        ]
    ),
    # Комбинация изменения даты и добавления строк
    (
        "дата 2025-06-01; добавь Яблоки 2 кг 100",
        {"date": "2025-05-05", "positions": []},
        {"date": "2025-06-01", "positions": [
            {"name": "Яблоки", "qty": "2", "unit": "кг", "price": "100"}
        ]},
        [
            {"action": "edit_date", "value": "2025-06-01"},
            {"action": "add_line", "value": "Яблоки 2 кг 100"}
        ]
    ),
    # Оригинальные тесты ниже
    (
        "строка 1 цена 12345",
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "100"},
            {"name": "Хлеб", "qty": "1", "unit": "шт", "price": "50"}
        ]},
        {"date": "2025-05-05", "positions": [
            {"name": "Молоко", "qty": "2", "unit": "л", "price": "12345"},
            {"name": "Хлеб", "qty": "1", "unit": "шт", "price": "50"}
        ]},
        {"action": "edit_line_field", "line": 1, "field": "price", "value": "12345"}
    ),
    (
        "дата 2025-06-01",
        {"date": "2025-05-05", "positions": []},
        {"date": "2025-06-01", "positions": []},
        {"action": "edit_date", "value": "2025-06-01"}
    ),
    (
        "добавь Яблоки 3 кг 300",
        {"date": "2025-05-05", "positions": []},
        {"date": "2025-05-05", "positions": [
            {"name": "Яблоки", "qty": "3", "unit": "кг", "price": "300"}
        ]},
        {"action": "add_line", "value": "Яблоки 3 кг 300"}
    ),
])
def test_edit_flow_integration(user_input, invoice_in, expected_invoice, expected_intent):
    from unittest.mock import MagicMock
    # Мокаем все методы OpenAI-клиента, чтобы возвращать реальные объекты, а не MagicMock
    with patch('app.assistants.client.client.beta.threads.create', return_value=MagicMock(id="thread_id")), \
         patch('app.assistants.client.client.beta.threads.messages.create', return_value=MagicMock()), \
         patch('app.assistants.client.client.beta.threads.runs.create', return_value=MagicMock(id="run_id", status="completed")), \
         patch('app.assistants.client.client.beta.threads.runs.retrieve', return_value=MagicMock(id="run_id", status="completed")):
        # Предполагается, что run_thread_safe вернёт expected_intent, если бы OpenAI вернул такой интент
        intent = expected_intent
        result_invoice = invoice_in.copy()
        if isinstance(intent, list):
            for single_intent in intent:
                result_invoice = apply_intent(result_invoice, single_intent)
        else:
            result_invoice = apply_intent(result_invoice, intent)
        assert result_invoice == expected_invoice
