import pytest

from app.edit import free_parser


@pytest.fixture
def invoice_example():
    return {
        "date": "",
        "positions": [
            {"name": "Milk", "qty": "2", "unit": "l", "price": "100"},
            {"name": "Bread", "qty": "1", "unit": "pc", "price": "50"},
        ],
    }


def test_edit_date(invoice_example):
    intent = free_parser.detect_intent("дата — 26 апреля 2025")
    new_invoice = free_parser.apply_edit(invoice_example, intent)
    assert new_invoice["date"] == "26 апреля 2025"


def test_edit_line_field(invoice_example):
    intent = free_parser.detect_intent("строка 2 цена 90")
    new_invoice = free_parser.apply_edit(invoice_example, intent)
    assert new_invoice["positions"][1]["price"] == "90"


def test_remove_line(invoice_example):
    intent = free_parser.detect_intent("удали 1")
    new_invoice = free_parser.apply_edit(invoice_example, intent)
    assert len(new_invoice["positions"]) == 1
    assert new_invoice["positions"][0]["name"] == "Bread"


def test_add_line(invoice_example):
    intent = free_parser.detect_intent("добавь Cheese 5 kg 450")
    new_invoice = free_parser.apply_edit(invoice_example, intent)
    assert len(new_invoice["positions"]) == 3
    assert new_invoice["positions"][2]["name"] == "Cheese"
    assert new_invoice["positions"][2]["qty"] == "5"
    assert new_invoice["positions"][2]["unit"] == "kg"
    assert new_invoice["positions"][2]["price"] == "450"


def test_finish_intent():
    intent = free_parser.detect_intent("готово")
    assert intent["action"] == "finish"


def test_unknown_intent():
    intent = free_parser.detect_intent("что-то непонятное")
    assert intent["action"] == "unknown"
