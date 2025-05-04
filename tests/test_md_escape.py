import pytest
from app.utils.md import escape_v2, escape_md

@pytest.mark.parametrize("raw,expected", [
    ("- price_per_kg *bold* _it_", r"\- price\_per\_kg \*bold\* \_it\_"),
    ("abc `def` ghi", r"abc \`def\` ghi"),
    ("[link](url)", r"\[link\]\(url\)"),
    ("sk-xxx", r"sk\-xxx"),
    ("#hashtag", r"\#hashtag"),  # Добавляем тест для # символа
])
def test_escape_md_basic(raw, expected):
    formatted = escape_md(raw)
    # All special chars must be escaped
    for char in ["-", "_", "*", "`", "[", "]", "(", ")", "#"]:
        assert char not in formatted or f"\\{char}" in formatted
    # Check expected substring
    assert expected in formatted

def test_escape_v2_with_code_blocks():
    """Проверяет экранирование с сохранением блоков кода"""
    input_text = """Текст *с форматированием* и #хэштегами
```
Блок кода с #символами, которые не должны экранироваться!
function test() { return 2 + 2; }
```
И ещё *форматированный* текст с [ссылкой](https://example.com)"""

    result = escape_v2(input_text)
    
    # Проверяем, что форматирование экранировано
    assert r"\*с форматированием\*" in result
    assert r"\#хэштегами" in result
    assert r"\*форматированный\*" in result
    assert r"\[ссылкой\]\(https://example\.com\)" in result
    
    # Проверяем, что в блоке кода НЕТ экранирования
    assert "Блок кода с #символами" in result  # # без экранирования
    assert "function test() { return 2 + 2; }" in result

def test_escape_v2_multiple_code_blocks():
    """Проверяет экранирование с несколькими блоками кода"""
    input_text = """Текст с *форматированием*
```
Первый блок кода #1
```
Текст между блоками с #хэштегом
```
Второй блок кода #2
```
Финальный *текст* с форматированием"""

    result = escape_v2(input_text)
    
    # Проверяем экранирование вне блоков кода
    assert r"\*форматированием\*" in result
    assert r"\#хэштегом" in result
    assert r"\*текст\*" in result
    
    # Проверяем отсутствие экранирования в блоках кода
    assert "Первый блок кода #1" in result
    assert "Второй блок кода #2" in result

def test_escape_v2_without_code_blocks():
    """Проверяет обычное экранирование без блоков кода"""
    input_text = "Простой текст с #хэштегом и *звездочками*"
    result = escape_v2(input_text)
    
    assert r"\#хэштегом" in result
    assert r"\*звездочками\*" in result

def test_escape_v2_edge_cases():
    """Проверяет граничные случаи для функции escape_v2"""
    # Пустой текст
    assert escape_v2("") == ""
    
    # None
    assert escape_v2(None) == ""
    
    # Только блок кода
    code_block = escape_v2("```\nТолько код #1\n```") 
    assert "Только код #1" in code_block
    assert r"\#1" not in code_block
