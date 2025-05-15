import os
import csv
from app import alias

def test_read_aliases_empty(tmp_path):
    path = tmp_path / "aliases.csv"
    result = alias.read_aliases(str(path))
    assert result == {}

def test_add_alias_and_read(tmp_path):
    path = tmp_path / "aliases.csv"
    ok = alias.add_alias("TestAlias", "12345", str(path))
    assert ok
    aliases = alias.read_aliases(str(path))
    assert "testalias" in aliases
    assert aliases["testalias"] == ("12345", "testalias")

def test_add_alias_duplicate(tmp_path):
    path = tmp_path / "aliases.csv"
    alias.add_alias("TestAlias", "12345", str(path))
    ok = alias.add_alias("TestAlias", "12345", str(path))
    assert not ok

def test_learn_from_invoice_partial(tmp_path):
    path = tmp_path / "aliases.csv"
    positions = [
        {"status": "partial", "name": "Green Apple", "matched_product": {"id": "p1"}},
        {"status": "partial", "name": "Red Tomato", "matched_product": {"id": "p2"}, "match_reason": "partial"},
        {"status": "ok", "name": "Banana", "matched_product": {"id": "p3"}},
        {"status": "partial", "name": "", "matched_product": {"id": "p4"}},
        {"status": "partial", "name": "Yellow Pepper", "matched_product": None},
    ]
    count, aliases_added = alias.learn_from_invoice(positions, str(path))
    # Должно добавить Green Apple и Red Tomato
    assert count == 2
    assert "Green Apple" in aliases_added
    assert "Red Tomato" in aliases_added
    aliases_dict = alias.read_aliases(str(path))
    assert "green apple" in aliases_dict
    assert "red tomato" in aliases_dict 