import pytest
from app.assistants.client import parse_assistant_output, EditCommand

# --- RED TESTS: Старый формат ---
def test_parse_single_action():
    raw = '{"action": "set_qty", "row": 2, "qty": "5"}'
    cmds = parse_assistant_output(raw)
    assert isinstance(cmds, list)
    assert len(cmds) == 1
    assert isinstance(cmds[0], EditCommand)
    assert cmds[0].action == "set_qty"
    assert cmds[0].row == 2
    assert cmds[0].qty == "5"

# --- RED TESTS: Новый формат (массив) ---
def test_parse_actions_array():
    raw = '{"actions": [{"action": "set_qty", "row": 2, "qty": "5"}, {"action": "set_name", "row": 1, "name": "Milk"}]}'
    cmds = parse_assistant_output(raw)
    assert isinstance(cmds, list)
    assert len(cmds) == 2
    assert cmds[0].action == "set_qty"
    assert cmds[1].action == "set_name"
    assert cmds[1].name == "Milk"

# --- RED TEST: Нет action(s) ---
def test_parse_missing_action():
    raw = '{"foo": 123}'
    with pytest.raises(ValueError, match="Neither 'action' nor 'actions' found"):
        parse_assistant_output(raw)

# --- RED TEST: Нет action в массиве ---
def test_parse_missing_action_in_array():
    raw = '{"actions": [{"row": 2}]}'
    with pytest.raises(ValueError, match="Missing 'action' field in response"):
        parse_assistant_output(raw)

# --- RED TEST: row < 1 ---
def test_parse_row_less_than_one():
    raw = '{"action": "set_qty", "row": 0, "qty": "5"}'
    with pytest.raises(ValueError, match="row must be >= 1 for action set_qty"):
        parse_assistant_output(raw)
