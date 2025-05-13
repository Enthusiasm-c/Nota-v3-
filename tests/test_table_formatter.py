from app.utils.table_formatter import text_to_markdown_table, parse_table_line

def test_parse_table_line():
    # Тест базового случая
    line = "1 mushroom 1 kg 40 000"
    name, qty, unit, price = parse_table_line(line)
    assert name == "mushroom"
    assert qty == "1"
    assert unit == "kg"
    assert price == "40000"
    
    # Тест с составным названием
    line = "2 green paprika 2 pcs 15 000"
    name, qty, unit, price = parse_table_line(line)
    assert name == "green paprika"
    assert qty == "2"
    assert unit == "pcs"
    assert price == "15000"
    
    # Тест с IDR в цене
    line = "3 tomato 0.5 kg 25 000 IDR"
    name, qty, unit, price = parse_table_line(line)
    assert name == "tomato"
    assert qty == "0.5"
    assert unit == "kg"
    assert price == "25000"

def test_text_to_markdown_table():
    input_text = """# NAME                   QTY     UNIT   PRICE
1 mushroom               1       kg     40 000
IDR
2 Romana                1       kg     55 000
IDR
3 green paprika         2       pcs    15 000
IDR"""
    
    expected_output = """| # | Name | Quantity | Unit | Unit Price (IDR) |
|---|------|----------|------|------------------|
| 1 | mushroom | 1 | kg | 40000 |
| 2 | Romana | 1 | kg | 55000 |
| 3 | green paprika | 2 | pcs | 15000 |
"""
    
    result = text_to_markdown_table(input_text)
    # Заменяем \n на реальные переносы строк для сравнения
    result = result.replace('\\n', '\n')
    assert result == expected_output 