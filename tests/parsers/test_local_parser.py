import pytest
import asyncio
from unittest.mock import patch, MagicMock, ANY
from app.parsers.local_parser import parse_command, parse_command_async

# Fixtures for mock sub-parsers (re-used from test_command_parser or could be defined here)
@pytest.fixture
def mock_parse_date_command_local(): # Renamed to avoid conflict if tests run together
    with patch("app.parsers.local_parser.parse_date_command") as mock:
        yield mock

@pytest.fixture
def mock_parse_line_command_local(): # Renamed
    with patch("app.parsers.local_parser.parse_line_command") as mock:
        yield mock

# Tests for the synchronous parse_command
def test_parse_command_date_success(mock_parse_date_command_local, mock_parse_line_command_local):
    expected_result = {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}
    mock_parse_date_command_local.return_value = expected_result
    text = "date 2023-01-01"
    
    result = parse_command(text)
    
    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_not_called()
    assert result == expected_result

def test_parse_command_line_success_after_date_fail(mock_parse_date_command_local, mock_parse_line_command_local):
    mock_parse_date_command_local.return_value = None # Date parser fails
    expected_result = {"action": "edit_price", "line": 0, "value": 100, "source": "local_parser"}
    mock_parse_line_command_local.return_value = expected_result
    text = "line 1 price 100"
    
    result = parse_command(text)
    
    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_called_once_with(text) # No invoice_lines for local_parser's direct call
    assert result == expected_result

def test_parse_command_all_local_parsers_fail(mock_parse_date_command_local, mock_parse_line_command_local):
    mock_parse_date_command_local.return_value = None
    # parse_line_command might return a dict with "action":"unknown" or a more specific error.
    # local_parser checks if the result is non-None (truthy). If line_parser returns an "unknown" dict, it's still truthy.
    # The logic in local_parser is `if line_result: return line_result`.
    # So, if line_parser itself returns an "unknown" action, local_parser will return that.
    # The final "unknown" is only if line_parser returns None.
    # Let's test the case where line_parser returns None (or something falsy).
    mock_parse_line_command_local.return_value = None 
    text = "unparseable by local means"
    
    result = parse_command(text)
    
    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_called_once_with(text)
    
    assert result == {
        "action": "unknown",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "local_parser"
    }

def test_parse_command_line_parser_returns_unknown_is_forwarded(mock_parse_date_command_local, mock_parse_line_command_local):
    mock_parse_date_command_local.return_value = None
    # line_parser itself might determine an action is "unknown" but provide more details
    line_parser_unknown_result = {"action": "unknown", "error": "specific_line_error", "source": "line_parser_source"}
    mock_parse_line_command_local.return_value = line_parser_unknown_result
    text = "some line related command that line_parser handles but deems unknown"

    result = parse_command(text)

    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_called_once_with(text)
    assert result == line_parser_unknown_result # local_parser should forward this specific unknown


@patch("time.time") # Mock time to check logging of elapsed_ms
def test_parse_command_logging_elapsed_time(mock_time, mock_parse_date_command_local, mock_parse_line_command_local, caplog):
    # Simulate time progression
    mock_time.side_effect = [1000.0, 1000.15] # Start time, end time for date_parser
    
    expected_result = {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}
    mock_parse_date_command_local.return_value = expected_result
    text = "date 2023-01-01"
    
    with caplog.at_level("INFO"):
        result = parse_command(text)
    
    assert result == expected_result
    assert "Локальный парсер обработал команду даты за 150.0 мс" in caplog.text # 0.15s = 150ms

    # Reset for next scenario
    caplog.clear()
    mock_time.side_effect = [2000.0, 2000.05, 2000.25] # Start, after date_fail, after line_success
    mock_parse_date_command_local.return_value = None
    expected_line_result = {"action": "edit_price", "line": 0, "value": 100}
    mock_parse_line_command_local.return_value = expected_line_result
    text_line = "line 1 price 100"

    with caplog.at_level("INFO"):
        result_line = parse_command(text_line)
    
    assert result_line == expected_line_result
    assert "Локальный парсер обработал команду редактирования строки за 200.0 мс" in caplog.text # (2000.25 - 2000.05) = 0.20s = 200ms
                                                                                             # Corrected: (2000.25 - 2000.0) = 0.25s = 250ms
                                                                                             # The start_time is captured at the very beginning.
    # Re-evaluating the log message based on code: elapsed_ms = (time.time() - start_time) * 1000
    # So for the second case: (2000.25 - 2000.0) * 1000 = 250.0 ms
    assert "Локальный парсер обработал команду редактирования строки за 250.0 мс" in caplog.text


# Tests for the asynchronous parse_command_async
@pytest.mark.asyncio
async def test_parse_command_async_date_success(mock_parse_date_command_local, mock_parse_line_command_local):
    expected_result = {"action": "set_date", "value": "2023-01-01", "source": "date_parser"}
    mock_parse_date_command_local.return_value = expected_result
    text = "date 2023-01-01"
    
    # Mock run_in_executor to directly call the function for easier testing of the wrapped logic
    with patch("asyncio.get_event_loop") as mock_get_loop:
        mock_loop_instance = mock_get_loop.return_value
        # Make run_in_executor call the target function directly with its args
        mock_loop_instance.run_in_executor = AsyncMock(side_effect=lambda _, func, *args: func(*args))

        result = await parse_command_async(text)
    
    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_not_called()
    assert result == expected_result
    mock_loop_instance.run_in_executor.assert_called_once_with(None, ANY, text) # ANY for parse_command function


@pytest.mark.asyncio
async def test_parse_command_async_all_fail(mock_parse_date_command_local, mock_parse_line_command_local):
    mock_parse_date_command_local.return_value = None
    mock_parse_line_command_local.return_value = None # Signifies line parser also couldn't find a match
    text = "unparseable by local means"

    with patch("asyncio.get_event_loop") as mock_get_loop:
        mock_loop_instance = mock_get_loop.return_value
        mock_loop_instance.run_in_executor = AsyncMock(side_effect=lambda _, func, *args: func(*args))
        
        result = await parse_command_async(text)

    mock_parse_date_command_local.assert_called_once_with(text)
    mock_parse_line_command_local.assert_called_once_with(text)
    assert result == {
        "action": "unknown",
        "user_message": "I couldn't understand your command. Please try again with a simpler format.",
        "source": "local_parser"
    }
    mock_loop_instance.run_in_executor.assert_called_once_with(None, ANY, text)

```
