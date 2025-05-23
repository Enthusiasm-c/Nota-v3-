from app.utils.md import escape_html, escape_v2


def test_escape_html_basic():
    import html

    cases = [
        ("<b>bold</b>", "&lt;b&gt;bold&lt;/b&gt;"),
        ("Fish & Chips", "Fish &amp; Chips"),
        ("'quote' and \"double\"", "&#x27;quote&#x27; and &quot;double&quot;"),
        ("<script>alert('xss')</script>", "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"),
        ("#hashtag!", "#hashtag!"),  # HTML escape не трогает # или !
    ]
    for raw, expected in cases:
        assert escape_html(raw) == expected
        # Проверяем, что результат совпадает с html.escape
        assert escape_html(raw) == html.escape(raw)


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
