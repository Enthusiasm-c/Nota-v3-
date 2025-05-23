import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open
from app.alias import read_aliases, add_alias, learn_from_invoice


def test_read_aliases():
    aliases_dict = read_aliases("data/aliases.csv")
    assert isinstance(aliases_dict, dict)
    # Add more specific tests here


def test_add_alias():
    # Add specific tests for add_alias function
    pass


def test_learn_from_invoice():
    # Add specific tests for learn_from_invoice function
    pass


def test_color_prefix_detection():
    positions = [
        {
            "status": "partial",
            "name": "green apple",
            "matched_product": {"id": "1"},
            "match_reason": "partial"
        },
        {
            "status": "partial",
            "name": "red tomato",
            "matched_product": {"id": "2"},
            "match_reason": "partial"
        }
    ]
    
    with patch("app.alias.add_alias") as mock_add:
        mock_add.return_value = True
        added_count, added_aliases = learn_from_invoice(positions)
        assert "green apple" in added_aliases
        assert "red tomato" in added_aliases


def test_read_aliases_empty(tmp_path):
    path = tmp_path / "aliases.csv"
    result = read_aliases(str(path))
    assert result == {}


def test_add_alias_and_read(tmp_path):
    path = tmp_path / "aliases.csv"
    ok = add_alias("TestAlias", "12345", str(path))
    assert ok
    aliases = read_aliases(str(path))
    assert "testalias" in aliases
    assert aliases["testalias"] == ("12345", "testalias")


def test_add_alias_duplicate(tmp_path):
    path = tmp_path / "aliases.csv"
    add_alias("TestAlias", "12345", str(path))
    ok = add_alias("TestAlias", "12345", str(path))
    assert not ok


def test_learn_from_invoice_partial(tmp_path):
    path = tmp_path / "aliases.csv"
    positions = [
        {"status": "partial", "name": "Green Apple", "matched_product": {"id": "p1"}},
        {
            "status": "partial",
            "name": "Red Tomato",
            "matched_product": {"id": "p2"},
            "match_reason": "partial",
        },
        {"status": "ok", "name": "Banana", "matched_product": {"id": "p3"}},
        {"status": "partial", "name": "", "matched_product": {"id": "p4"}},
        {"status": "partial", "name": "Yellow Pepper", "matched_product": None},
    ]
    count, aliases_added = learn_from_invoice(positions, str(path))
    # Должно добавить Green Apple и Red Tomato
    assert count == 2
    assert "Green Apple" in aliases_added
    assert "Red Tomato" in aliases_added
    aliases_dict = read_aliases(str(path))
    assert "green apple" in aliases_dict
    assert "red tomato" in aliases_dict