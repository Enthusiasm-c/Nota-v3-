import pytest
from unittest.mock import patch, MagicMock
from app.parsers.command_parser import parse_command, parse_compound_command, _parse_compound_line_command

# Fixtures for mock parsers
@pytest.fixture
def mock_normalize_text():
    with patch("app.parsers.command_parser.normalize_text", side_effect=lambda x: x.lower()) as mock: # Simple normalization
        yield mock

@pytest.fixture
def mock_split_command():
    with patch("app.parsers.command_parser.split_command") as mock:
        yield mock

@pytest.fixture
def mock_parse_date_command():
    with patch("app.parsers.command_parser.parse_date_command") as mock:
        yield mock

@pytest.fixture
def mock_parse_line_command():
    with patch("app.parsers.command_parser.parse_line_command") as mock:
        yield mock

@pytest.fixture
def mock_detect_intent():
    with patch("app.parsers.command_parser.detect_intent") as mock:
        yield mock

# Tests for parse_command
def test_parse_command_empty_input(mock_normalize_text):
    result = parse_command("")
    assert result == {"action": "unknown", "error": "empty_command", "source": "integrated_parser"}
    mock_normalize_text.assert_not_called() # Should return before normalization

def test_parse_command_date_command_success(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}
    text = "date 2023-01-01"
    result = parse_command(text)
    
    mock_normalize_text.assert_called_once_with(text)
    mock_parse_date_command.assert_called_once_with(text)
    mock_parse_line_command.assert_not_called()
    mock_detect_intent.assert_not_called()
    assert result == {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}

def test_parse_command_date_command_add_source_if_missing(
    mock_normalize_text, mock_parse_date_command
):
    # Simulate date_parser not adding its own source
    mock_parse_date_command.return_value = {"action": "set_date", "value": "2023-01-01"} 
    text = "date 2023-01-01"
    result = parse_command(text)
    assert result == {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}


def test_parse_command_line_command_success(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = None
    mock_parse_line_command.return_value = {"action": "edit_price", "line": 0, "value": 100, "source": "local_parser"}
    text = "line 1 price 100"
    result = parse_command(text, invoice_lines=5)
    
    mock_normalize_text.assert_called_once_with(text)
    mock_parse_date_command.assert_called_once_with(text)
    mock_parse_line_command.assert_called_once_with(text, 5)
    mock_detect_intent.assert_not_called()
    assert result == {"action": "edit_price", "line": 0, "value": 100, "source": "local_parser"}

@patch("app.parsers.command_parser._parse_compound_line_command")
def test_parse_command_compound_line_success(
    mock_internal_compound_parser, mock_normalize_text, mock_parse_date_command, 
    mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = None
    mock_parse_line_command.return_value = {"action": "unknown", "error": "some_error"} # Line parser fails
    # _parse_compound_line_command returns a list, parse_command should take the first
    mock_internal_compound_parser.return_value = [
        {"action": "edit_name", "line": 0, "value": "Compound Name", "source": "local_parser"}
    ]
    text = "line 1: name Compound Name"
    result = parse_command(text, invoice_lines=2)

    mock_normalize_text.assert_called_once_with(text)
    mock_parse_date_command.assert_called_once_with(text)
    mock_parse_line_command.assert_called_once_with(text, 2)
    mock_internal_compound_parser.assert_called_once_with(text, 2)
    mock_detect_intent.assert_not_called()
    assert result == {"action": "edit_name", "line": 0, "value": "Compound Name", "source": "local_parser"}


def test_parse_command_free_parser_success(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, 
    mock_detect_intent
):
    mock_parse_date_command.return_value = None
    mock_parse_line_command.return_value = {"action": "unknown", "error": "some_error"} # Line parser fails
    # _parse_compound_line_command (internal) will also return [] if no match
    with patch("app.parsers.command_parser._parse_compound_line_command", return_value=[]):
        mock_detect_intent.return_value = {"action": "free_edit", "details": "do something", "source": "free_parser"}
        text = "do something freely"
        result = parse_command(text)
        
        mock_normalize_text.assert_called_once_with(text)
        mock_parse_date_command.assert_called_once_with(text)
        mock_parse_line_command.assert_called_once_with(text, None)
        mock_detect_intent.assert_called_once_with(text)
        assert result == {"action": "free_edit", "details": "do something", "source": "free_parser"}

def test_parse_command_free_parser_add_source_if_missing(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = None
    mock_parse_line_command.return_value = {"action": "unknown"}
    with patch("app.parsers.command_parser._parse_compound_line_command", return_value=[]):
      mock_detect_intent.return_value = {"action": "free_edit", "details": "do something"} # No source
      text = "do something freely"
      result = parse_command(text)
      assert result == {"action": "free_edit", "details": "do something", "source": "free_parser"}


def test_parse_command_all_parsers_fail(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = None
    # parse_line_command returns a dict with "action":"unknown" when it fails to parse but matches a general structure
    # or it might return a more specific error if, e.g., line number is invalid.
    # Let's assume it returns a specific error for this test.
    mock_parse_line_command.return_value = {"action": "unknown", "error": "invalid_line_format_specific"}
    with patch("app.parsers.command_parser._parse_compound_line_command", return_value=[]):
        mock_detect_intent.return_value = {"action": "unknown", "error": "free_parser_unknown"}
        text = "unparseable gibberish"
        result = parse_command(text)
        
        mock_normalize_text.assert_called_once_with(text)
        # Assert all parsers were called
        mock_parse_date_command.assert_called_once_with(text)
        mock_parse_line_command.assert_called_once_with(text, None)
        mock_detect_intent.assert_called_once_with(text)
        
        # Check the error structure, it should prioritize the error from line_parser if available
        assert result == {
            "action": "unknown", 
            "error": "invalid_line_format_specific", # Error from line_result
            "user_message": "I didn't understand your command. Could you please try rephrasing it?",
            "source": "integrated_parser",
            "original_text": text
        }

def test_parse_command_all_parsers_fail_no_specific_error_from_line_parser(
    mock_normalize_text, mock_parse_date_command, mock_parse_line_command, mock_detect_intent
):
    mock_parse_date_command.return_value = None
    # This time, line_parser returns a generic unknown without a specific error key
    mock_parse_line_command.return_value = {"action": "unknown"} 
    with patch("app.parsers.command_parser._parse_compound_line_command", return_value=[]):
        mock_detect_intent.return_value = {"action": "unknown", "error": "free_parser_unknown"}
        text = "unparseable gibberish"
        result = parse_command(text)
        
        # Check the error structure, should be a generic unknown_command
        assert result == {
            "action": "unknown", 
            "error": "unknown_command", # Generic error as line_result had no specific error
            "user_message": "I didn't understand your command. Could you please try rephrasing it?",
            "source": "integrated_parser",
            "original_text": text
        }

# Tests for _parse_compound_line_command (internal function)
@patch("app.parsers.command_parser.parse_line_command") # Mock the call to the actual line parser
def test_parse_compound_line_command_single_line_single_field(mock_plc):
    mock_plc.return_value = {"action": "edit_name", "line": 0, "value": "Test Product", "source": "local_parser"}
    text = "строка 1: название Test Product"
    results = _parse_compound_line_command(text, invoice_lines=1)
    
    assert len(results) == 1
    assert results[0] == {"action": "edit_name", "line": 0, "value": "Test Product", "source": "local_parser"}
    mock_plc.assert_called_once_with("строка 1 название Test Product", 1)

@patch("app.parsers.command_parser.parse_line_command")
def test_parse_compound_line_command_single_line_multiple_fields(mock_plc):
    def plc_side_effect(cmd_text, lines):
        if "название Test Product" in cmd_text:
            return {"action": "edit_name", "line": 0, "value": "Test Product", "source": "local_parser"}
        elif "цена 123" in cmd_text:
            return {"action": "edit_price", "line": 0, "value": 123.0, "source": "local_parser"}
        return None
    mock_plc.side_effect = plc_side_effect
    
    text = "line 1: name Test Product; price 123"
    results = _parse_compound_line_command(text, invoice_lines=1)
    
    assert len(results) == 2
    assert {"action": "edit_name", "line": 0, "value": "Test Product", "source": "local_parser"} in results
    assert {"action": "edit_price", "line": 0, "value": 123.0, "source": "local_parser"} in results
    assert mock_plc.call_count == 2

@patch("app.parsers.command_parser.parse_line_command")
def test_parse_compound_line_command_multiple_lines_defined(mock_plc):
    # _parse_compound_line_command processes multiple "line X:" definitions in one text block
    def plc_side_effect(cmd_text, lines):
        if "строка 1 название Product A" in cmd_text:
            return {"action": "edit_name", "line": 0, "value": "Product A"}
        elif "строка 2 цена 200" in cmd_text:
            return {"action": "edit_price", "line": 1, "value": 200.0}
        return None
    mock_plc.side_effect = plc_side_effect

    text = "строка 1: название Product A строка 2: цена 200"
    results = _parse_compound_line_command(text, invoice_lines=2)
    
    assert len(results) == 2
    assert {"action": "edit_name", "line": 0, "value": "Product A"} in results
    assert {"action": "edit_price", "line": 1, "value": 200.0} in results

@patch("app.parsers.command_parser.parse_line_command")
def test_parse_compound_line_command_invalid_line_number(mock_plc):
    text = "line 0: name Fail" # Line numbers are 1-based in input
    results = _parse_compound_line_command(text, invoice_lines=1)
    assert len(results) == 1
    assert results[0] == {"action": "unknown", "error": "invalid_line_number"}
    mock_plc.assert_not_called()

@patch("app.parsers.command_parser.parse_line_command")
def test_parse_compound_line_command_line_out_of_range(mock_plc):
    text = "line 2: name Fail"
    results = _parse_compound_line_command(text, invoice_lines=1) # Only 1 line in invoice
    assert len(results) == 1
    assert results[0] == {"action": "unknown", "error": "line_out_of_range", "line": 1} # 0-indexed
    mock_plc.assert_not_called()

@patch("app.parsers.command_parser.parse_line_command")
def test_parse_compound_line_command_field_parse_fail(mock_plc):
    mock_plc.return_value = {"action": "unknown", "error": "parse_error_detail"} # Field parser fails
    text = "line 1: unparseable_field value"
    results = _parse_compound_line_command(text, invoice_lines=1)
    # If parse_line_command returns unknown, _parse_compound_line_command does not add it
    assert len(results) == 0 
    mock_plc.assert_called_once_with("строка 1 unparseable_field value", 1)


# Tests for parse_compound_command (public function)
@patch("app.parsers.command_parser._parse_compound_line_command")
@patch("app.parsers.command_parser.split_command")
@patch("app.parsers.command_parser.parse_command") # Mock the recursive call
def test_parse_compound_command_uses_internal_compound_parser_first(
    mock_pc, mock_sc, mock_internal_compound_parser
):
    expected_results = [{"action": "edit_name", "line": 0, "value": "Compound Name"}]
    mock_internal_compound_parser.return_value = expected_results
    text = "line 1: name Compound Name"
    
    results = parse_compound_command(text, invoice_lines=1)
    
    mock_internal_compound_parser.assert_called_once_with(text, 1)
    mock_sc.assert_not_called() # split_command should not be called
    mock_pc.assert_not_called() # parse_command (recursive) should not be called
    assert results == expected_results

@patch("app.parsers.command_parser._parse_compound_line_command", return_value=[]) # Internal fails
@patch("app.parsers.command_parser.split_command")
@patch("app.parsers.command_parser.parse_command") # Mock the recursive call
def test_parse_compound_command_falls_back_to_split_and_parse(
    mock_pc, mock_sc, mock_internal_compound_parser_empty
):
    text = "command1 ; command2"
    mock_sc.return_value = ["command1", "command2"] # split_command returns parts
    
    # parse_command will be called for each part
    mock_pc.side_effect = [
        {"action": "result1"},
        {"action": "result2"}
    ]
    
    results = parse_compound_command(text, invoice_lines=1)
    
    mock_internal_compound_parser_empty.assert_called_once_with(text, 1)
    mock_sc.assert_called_once_with(text)
    assert mock_pc.call_count == 2
    mock_pc.assert_any_call("command1", 1)
    mock_pc.assert_any_call("command2", 1)
    assert results == [{"action": "result1"}, {"action": "result2"}]

```
