import pytest
from app.utils.md import escape_v2

@pytest.mark.parametrize("raw,expected", [
    ("- price_per_kg *bold* _it_", r"\- price\_per\_kg \*bold\* \_it\_"),
    ("abc `def` ghi", r"abc \`def\` ghi"),
    ("```code```", r"\\`\\`\\`code\\`\\`\\`"),
    ("[link](url)", r"\[link\]\(url\)"),
    ("sk-xxx", r"sk\-xxx"),
])
def test_escape_v2(raw, expected):
    formatted = escape_v2(raw)
    # All special chars must be escaped
    for char in ["-", "_", "*", "`", "[", "]", "(", ")"]:
        assert char not in formatted or f"\\{char}" in formatted
    # For triple backticks, check explicit pattern
    if raw.startswith("```"):
        assert formatted.startswith(r"\\`\\`\\`")
    # Check expected substring
    assert expected in formatted
