import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User
from aiogram.fsm.context import FSMContext

from app.handlers.edit_core import process_user_edit

# Helper to create a mock FSMContext
def get_mock_fsm_context(initial_data=None):
    mock_context = AsyncMock(spec=FSMContext)
    current_data = initial_data if initial_data is not None else {}

    async def get_data():
        return current_data.copy()

    async def update_data(new_data):
        current_data.update(new_data)
        return current_data.copy()

    async def set_state(state_name):
        current_data['_state'] = state_name

    async def clear():
        current_data.clear()

    mock_context.get_data = AsyncMock(side_effect=get_data)
    mock_context.update_data = AsyncMock(side_effect=update_data)
    mock_context.set_state = AsyncMock(side_effect=set_state)
    mock_context.clear = AsyncMock(side_effect=clear)
    return mock_context

# Helper to create a mock Message
def get_mock_message(user_id=123, text="some command"):
    mock_msg = AsyncMock(spec=Message)
    mock_msg.from_user = AsyncMock(spec=User)
    mock_msg.from_user.id = user_id
    mock_msg.text = text
    return mock_msg

@pytest.fixture
def mock_message():
    return get_mock_message()

@pytest.fixture
def mock_state():
    return get_mock_fsm_context()

@pytest.fixture
def mock_callbacks():
    return {
        "send_processing": AsyncMock(),
        "send_result": AsyncMock(),
        "send_error": AsyncMock(),
        "run_openai_intent": AsyncMock(),
        "fuzzy_suggester": AsyncMock(),
        "edit_state": AsyncMock(), # Added for completeness from edit_flow.py
    }

@pytest.mark.asyncio
async def test_edit_in_progress(mock_message, mock_state, mock_callbacks):
    """Test that if an edit is already in progress, an error message is sent."""
    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=True)):
        await process_user_edit(
            mock_message, mock_state, "some text", **mock_callbacks
        )
    mock_callbacks["send_error"].assert_called_once()
    assert "edit_in_progress" in mock_callbacks["send_error"].call_args[0][0]
    mock_callbacks["send_processing"].assert_not_called()
    # Ensure processing guard was not set to True again or False
    # This requires mocking set_processing_edit as well if we want to check its calls.

@pytest.mark.asyncio
async def test_cancel_command(mock_message, mock_state, mock_callbacks):
    """Test that 'cancel' command cancels the edit."""
    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing:
        
        await process_user_edit(
            mock_message, mock_state, "cancel", **mock_callbacks
        )
    
    mock_callbacks["send_result"].assert_called_once()
    assert "edit_cancelled" in mock_callbacks["send_result"].call_args[0][0]
    mock_state.set_state.assert_called_once_with(None)
    # Check that processing lock is released
    mock_set_processing.assert_any_call(mock_message.from_user.id, True) # Initial set
    mock_set_processing.assert_any_call(mock_message.from_user.id, False) # Release on cancel

@pytest.mark.asyncio
async def test_no_invoice_in_state(mock_message, mock_state, mock_callbacks):
    """Test error handling when no invoice is found in FSM state."""
    # mock_state is initialized with empty data by default
    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing:

        await process_user_edit(
            mock_message, mock_state, "some command", **mock_callbacks
        )

    mock_callbacks["send_error"].assert_called_once()
    assert "session_expired" in mock_callbacks["send_error"].call_args[0][0]
    mock_state.clear.assert_called_once()
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_successful_edit_flow_local_parser(mock_message, mock_callbacks):
    """Test a successful edit flow using the local parser."""
    initial_invoice_data = {"positions": [{"name": "Old Name", "qty": 1, "price": 10}]}
    state = get_mock_fsm_context({"invoice": initial_invoice_data, "lang": "en"})
    
    mock_intent_result = {"action": "edit_name", "line": 0, "value": "New Name"}
    mock_new_invoice_data = {"positions": [{"name": "New Name", "qty": 1, "price": 10}]}
    mock_match_results = [{"status": "ok", "name": "New Name"}]
    mock_report_text = "Report text"
    
    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)) as mock_local_parser, \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_new_invoice_data)) as mock_apply_intent, \
         patch("app.handlers.edit_core.load_products", MagicMock(return_value=[])) as mock_load_products, \
         patch("app.handlers.edit_core.match_positions", MagicMock(return_value=mock_match_results)) as mock_match_positions, \
         patch("app.handlers.edit_core.report.build_report", MagicMock(return_value=(mock_report_text, False))) as mock_build_report, \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)) as mock_parsed_to_dict: # bypass Pydantic if used

        await process_user_edit(
            mock_message, state, "line 1 name New Name", **mock_callbacks
        )

    mock_callbacks["send_processing"].assert_called_once()
    mock_local_parser.assert_called_once_with("line 1 name New Name")
    mock_callbacks["run_openai_intent"].assert_not_called() # OpenAI parser should not be called
    mock_apply_intent.assert_called_once_with(initial_invoice_data, mock_intent_result)
    mock_load_products.assert_called_once()
    mock_match_positions.assert_called_once_with(mock_new_invoice_data["positions"], [])
    
    updated_data = await state.get_data()
    assert updated_data["invoice"] == mock_new_invoice_data
    assert updated_data["unknown_count"] == 0
    assert updated_data["partial_count"] == 0
    
    mock_build_report.assert_called_once_with(mock_new_invoice_data, mock_match_results)
    mock_callbacks["send_result"].assert_called_once_with(mock_report_text)
    mock_callbacks["fuzzy_suggester"].assert_not_called() # No unknown items
    
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False) # Released


@pytest.mark.asyncio
async def test_successful_edit_flow_openai_parser(mock_message, mock_callbacks):
    """Test a successful edit flow using the OpenAI parser when local parser fails."""
    initial_invoice_data = {"positions": [{"name": "Old Name", "qty": 1, "price": 10}]}
    state = get_mock_fsm_context({"invoice": initial_invoice_data, "lang": "en"})
    
    mock_local_intent_unknown = {"action": "unknown"}
    mock_openai_intent_result = {"action": "edit_name", "line": 0, "value": "New Name OpenAI"}
    mock_new_invoice_data = {"positions": [{"name": "New Name OpenAI", "qty": 1, "price": 10}]}
    mock_match_results = [{"status": "ok", "name": "New Name OpenAI"}]
    mock_report_text = "OpenAI Report text"

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()), \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_local_intent_unknown)) as mock_local_parser, \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_new_invoice_data)) as mock_apply_intent, \
         patch("app.handlers.edit_core.load_products", MagicMock(return_value=[])), \
         patch("app.handlers.edit_core.match_positions", MagicMock(return_value=mock_match_results)), \
         patch("app.handlers.edit_core.report.build_report", MagicMock(return_value=(mock_report_text, False))), \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):
        
        # Ensure run_openai_intent is set and returns the desired result
        mock_callbacks["run_openai_intent"] = AsyncMock(return_value=mock_openai_intent_result)

        await process_user_edit(
            mock_message, state, "complex edit command", **mock_callbacks
        )

    mock_local_parser.assert_called_once_with("complex edit command")
    mock_callbacks["run_openai_intent"].assert_called_once_with("complex edit command")
    mock_apply_intent.assert_called_once_with(initial_invoice_data, mock_openai_intent_result)
    mock_callbacks["send_result"].assert_called_once_with(mock_report_text)


@pytest.mark.asyncio
async def test_parser_timeout(mock_message, mock_callbacks):
    """Test handling of parser timeout."""
    state = get_mock_fsm_context({"invoice": {"positions": []}, "lang": "en"})
    
    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(side_effect=asyncio.TimeoutError)):
        
        await process_user_edit(
            mock_message, state, "some command", **mock_callbacks
        )
    
    mock_callbacks["send_error"].assert_called_once()
    assert "openai_timeout" in mock_callbacks["send_error"].call_args[0][0] # Assumes local parser timeout leads to openai_timeout message
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_unknown_intent_after_parsing(mock_message, mock_callbacks):
    """Test handling when parser returns an unknown intent with a message."""
    state = get_mock_fsm_context({"invoice": {"positions": []}, "lang": "en"})
    mock_intent_unknown = {"action": "unknown", "user_message": "Specific unknown reason"}

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_unknown)):
        
        await process_user_edit(
            mock_message, state, "unknown command text", **mock_callbacks
        )
        
    mock_callbacks["send_error"].assert_called_once_with("Specific unknown reason")
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_apply_intent_failure(mock_message, mock_callbacks):
    """Test handling of failure during apply_intent."""
    state = get_mock_fsm_context({"invoice": {"positions": []}, "lang": "en"})
    mock_intent_result = {"action": "edit_name", "line": 0, "value": "New Name"}

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(side_effect=Exception("Apply failed"))) as mock_apply_intent, \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):

        await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )

    mock_callbacks["send_error"].assert_called_once()
    assert "Ошибка при применении изменений: Apply failed" in mock_callbacks["send_error"].call_args[0][0]
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)

@pytest.mark.asyncio
async def test_apply_intent_returns_none(mock_message, mock_callbacks):
    """Test handling when apply_intent returns None."""
    state = get_mock_fsm_context({"invoice": {"positions": []}, "lang": "en"})
    mock_intent_result = {"action": "edit_name", "line": 0, "value": "New Name"}

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=None)) as mock_apply_intent, \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):

        await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )

    mock_callbacks["send_error"].assert_called_once_with("Ошибка при применении изменений: инвойс не получен")
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_no_positions_after_apply_intent(mock_message, mock_callbacks):
    """Test handling when new_invoice has no positions after apply_intent."""
    state = get_mock_fsm_context({"invoice": {"positions": [{"name":"old"}]}, "lang": "en"})
    mock_intent_result = {"action": "delete_line", "line": 0} # Example intent
    mock_invoice_no_positions = {"positions": []} # No positions

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_invoice_no_positions)), \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):

        await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )

    mock_callbacks["send_error"].assert_called_once_with("Ошибка: после применения изменений в инвойсе отсутствуют позиции")
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_build_report_failure(mock_message, mock_callbacks):
    """Test handling of failure during report.build_report."""
    state = get_mock_fsm_context({"invoice": {"positions": [{"name": "Some Name"}]}, "lang": "en"})
    mock_intent_result = {"action": "edit_price", "line": 0, "value": 123}
    mock_new_invoice_data = {"positions": [{"name": "Some Name", "price": 123}]}
    mock_match_results = [{"status": "ok"}]

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_new_invoice_data)), \
         patch("app.handlers.edit_core.load_products", MagicMock(return_value=[])), \
         patch("app.handlers.edit_core.match_positions", MagicMock(return_value=mock_match_results)), \
         patch("app.handlers.edit_core.report.build_report", MagicMock(side_effect=Exception("Report failed"))), \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):
        
        await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )

    mock_callbacks["send_error"].assert_called_once()
    assert "Ошибка при формировании отчета: Report failed" in mock_callbacks["send_error"].call_args[0][0]
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False)


@pytest.mark.asyncio
async def test_fuzzy_suggester_called_for_unknown_item(mock_message, mock_callbacks):
    """Test that fuzzy_suggester is called when an item is 'unknown'."""
    initial_invoice_data = {"positions": [{"name": "Unknown Product", "qty": 1, "price": 10}]}
    state = get_mock_fsm_context({"invoice": initial_invoice_data, "lang": "en"})
    
    mock_intent_result = {"action": "noop"} # No change intent
    mock_new_invoice_data = initial_invoice_data # Stays the same
    # Simulate match_positions returning an 'unknown' status
    mock_match_results = [{"status": "unknown", "name": "Unknown Product"}] 
    mock_report_text = "Report with unknown"

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()), \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_new_invoice_data)), \
         patch("app.handlers.edit_core.load_products", MagicMock(return_value=[])), \
         patch("app.handlers.edit_core.match_positions", MagicMock(return_value=mock_match_results)) as mock_matcher, \
         patch("app.handlers.edit_core.report.build_report", MagicMock(return_value=(mock_report_text, True))), \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):
        
        mock_callbacks["fuzzy_suggester"] = AsyncMock(return_value=True) # Simulate suggestion was shown

        await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )

    mock_matcher.assert_called_once()
    mock_callbacks["fuzzy_suggester"].assert_called_once_with(
        mock_message, state, "Unknown Product", 0, "en"
    )
    # If fuzzy_suggester returns True (suggestion shown), send_result should NOT be called
    mock_callbacks["send_result"].assert_not_called()

@pytest.mark.asyncio
async def test_send_result_called_if_fuzzy_suggester_not_shown(mock_message, mock_callbacks):
    """Test that send_result is called if fuzzy_suggester is not active or doesn't show a suggestion."""
    initial_invoice_data = {"positions": [{"name": "Unknown Product", "qty": 1, "price": 10}]}
    state = get_mock_fsm_context({"invoice": initial_invoice_data, "lang": "en"})
    
    mock_intent_result = {"action": "noop"}
    mock_new_invoice_data = initial_invoice_data
    mock_match_results = [{"status": "unknown", "name": "Unknown Product"}] 
    mock_report_text = "Report with unknown"

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()), \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(return_value=mock_intent_result)), \
         patch("app.handlers.edit_core.apply_intent", MagicMock(return_value=mock_new_invoice_data)), \
         patch("app.handlers.edit_core.load_products", MagicMock(return_value=[])), \
         patch("app.handlers.edit_core.match_positions", MagicMock(return_value=mock_match_results)), \
         patch("app.handlers.edit_core.report.build_report", MagicMock(return_value=(mock_report_text, True))), \
         patch("app.handlers.edit_core.parsed_to_dict", MagicMock(side_effect=lambda x: x)):
        
        # Scenario 1: fuzzy_suggester is None
        mock_callbacks["fuzzy_suggester"] = None
        await process_user_edit(mock_message, state, "command", **mock_callbacks)
        mock_callbacks["send_result"].assert_called_once_with(mock_report_text)
        mock_callbacks["send_result"].reset_mock() # Reset for next scenario

        # Scenario 2: fuzzy_suggester returns False (no suggestion shown)
        mock_callbacks["fuzzy_suggester"] = AsyncMock(return_value=False)
        await process_user_edit(mock_message, state, "command", **mock_callbacks)
        mock_callbacks["send_result"].assert_called_once_with(mock_report_text)

@pytest.mark.asyncio
async def test_unexpected_exception_handling(mock_message, mock_callbacks):
    """Test handling of an unexpected exception during the process."""
    state = get_mock_fsm_context({"invoice": {"positions": []}, "lang": "en"})

    with patch("app.handlers.edit_core.is_processing_edit", AsyncMock(return_value=False)), \
         patch("app.handlers.edit_core.set_processing_edit", AsyncMock()) as mock_set_processing, \
         patch("app.handlers.edit_core.parse_command_async", AsyncMock(side_effect=Exception("Totally unexpected!"))):
        
        result = await process_user_edit(
            mock_message, state, "command", **mock_callbacks
        )
        assert result is False

    mock_callbacks["send_error"].assert_called_once()
    assert "unexpected" in mock_callbacks["send_error"].call_args[0][0]
    mock_set_processing.assert_any_call(mock_message.from_user.id, True)
    mock_set_processing.assert_any_call(mock_message.from_user.id, False) # Ensure lock is released

```
