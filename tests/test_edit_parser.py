from app.assistants.client import EditCommand, parse_assistant_output


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
    cmds = parse_assistant_output(raw)
    assert len(cmds) == 1
    assert cmds[0].action == "clarification_needed"
    assert (
        "clarification needed" in cmds[0].error.lower() or raw in cmds[0].error
    )  # Проверка на гибкое содержимое сообщения об ошибке


# --- RED TEST: Нет action в массиве ---
def test_parse_missing_action_in_array():
    raw = '{"actions": [{"row": 2}]}'
    cmds = parse_assistant_output(raw)
    assert len(cmds) == 1
    assert cmds[0].action == "clarification_needed"
    assert (
        "valid commands" in cmds[0].error
    )  # Проверяем только часть сообщения, а не точное соответствие


# --- TEST: Plain text (не JSON) ---
def test_parse_plain_text():
    raw = "Поменяй количество на 5"
    cmds = parse_assistant_output(raw)
    assert len(cmds) == 1
    assert cmds[0].action == "clarification_needed"
    assert raw in cmds[0].error  # Проверяем, что исходный текст содержится в сообщении об ошибке


# --- RED TEST: row < 1 ---
def test_parse_row_less_than_one():
    raw = '{"action": "set_qty", "row": 0, "qty": "5"}'
    cmds = parse_assistant_output(raw)
    assert len(cmds) == 1
    assert cmds[0].action == "clarification_needed"
    assert (
        "valid commands" in cmds[0].error
    )  # Проверяем только часть сообщения, а не точное соответствие
