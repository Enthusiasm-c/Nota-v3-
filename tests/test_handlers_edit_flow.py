"""Tests for app/handlers/edit_flow.py"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from aiogram import types
from aiogram.fsm.context import FSMContext

from app.handlers.edit_flow import (
    router,
    handle_edit_click,
    handle_free_edit_input,
    handle_cancel_edit,
    handle_inline_edit,
    handle_review_callback
)
from app.fsm.states import EditFree


class TestEditFlowHandlers:
    """Test edit flow handlers"""
    
    @pytest.mark.asyncio
    async def test_handle_edit_click(self):
        """Test handle_edit_click handler"""
        # Create mock callback query
        callback = Mock(spec=types.CallbackQuery)
        callback.data = "edit"
        callback.message = Mock(spec=types.Message)
        callback.message.message_id = 123
        callback.message.chat = Mock(id=456)
        callback.answer = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.set_state = AsyncMock()
        state.update_data = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"positions": []},
            "match_results": []
        })
        
        # Call handler
        await handle_edit_click(callback, state)
        
        # Verify
        callback.answer.assert_called_once()
        state.set_state.assert_called_once_with(EditFree.awaiting_free_edit)
        state.update_data.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.handlers.edit_flow.run_thread_safe')
    @patch('app.handlers.edit_flow.apply_intent')
    async def test_handle_free_edit_input_success(
        self,
        mock_apply_intent,
        mock_run_thread
    ):
        """Test successful free edit input handling"""
        # Setup mocks
        mock_run_thread.return_value = [
            {"action": "set_name", "row": 1, "name": "New Product"}
        ]
        mock_apply_intent.return_value = (
            {"positions": [{"name": "New Product"}]},
            [{"name": "New Product", "status": "ok"}],
            ["Applied: set_name"]
        )
        
        # Create mock message
        message = Mock(spec=types.Message)
        message.text = "строка 1 название New Product"
        message.answer = AsyncMock()
        message.edit_text = AsyncMock()
        message.chat = Mock(id=456)
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"positions": [{"name": "Old Product"}]},
            "match_results": [{"name": "Old Product", "status": "ok"}],
            "report_message_id": 789
        })
        state.update_data = AsyncMock()
        state.clear = AsyncMock()
        
        # Call handler
        await handle_free_edit_input(message, state)
        
        # Verify
        mock_run_thread.assert_called_once()
        mock_apply_intent.assert_called_once()
        message.answer.assert_called()
        state.clear.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.handlers.edit_flow.run_thread_safe')
    async def test_handle_free_edit_input_no_intent(
        self,
        mock_run_thread
    ):
        """Test free edit input with no intent recognized"""
        # Setup mocks
        mock_run_thread.return_value = []  # No intent
        
        # Create mock message
        message = Mock(spec=types.Message)
        message.text = "непонятная команда"
        message.answer = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"positions": []},
            "match_results": []
        })
        
        # Call handler
        await handle_free_edit_input(message, state)
        
        # Verify
        message.answer.assert_called_with(
            "❌ Не удалось распознать команду. Попробуйте еще раз или нажмите Отмена."
        )
    
    @pytest.mark.asyncio
    async def test_handle_cancel_edit(self):
        """Test cancel edit handler"""
        # Create mock callback query
        callback = Mock(spec=types.CallbackQuery)
        callback.data = "cancel_edit"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=types.Message)
        callback.message.edit_text = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.clear = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "report_text": "Original report"
        })
        
        # Call handler
        await handle_cancel_edit(callback, state)
        
        # Verify
        callback.answer.assert_called_with("❌ Редактирование отменено")
        state.clear.assert_called_once()
        callback.message.edit_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_inline_edit(self):
        """Test inline edit handler"""
        # Create mock callback query
        callback = Mock(spec=types.CallbackQuery)
        callback.data = "edit_name_1"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=types.Message)
        callback.message.edit_text = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.set_state = AsyncMock()
        state.update_data = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"positions": [{"name": "Product"}]},
            "match_results": [{"name": "Product", "status": "ok"}]
        })
        
        # Call handler
        await handle_inline_edit(callback, state)
        
        # Verify
        callback.answer.assert_called_once()
        state.set_state.assert_called_once()
        state.update_data.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_review_callback_confirm(self):
        """Test review callback with confirm action"""
        # Create mock callback query
        callback = Mock(spec=types.CallbackQuery)
        callback.data = "confirm_invoice"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=types.Message)
        callback.message.edit_text = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.clear = AsyncMock()
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"supplier": "Test"},
            "match_results": []
        })
        
        # Call handler
        await handle_review_callback(callback, state)
        
        # Verify
        callback.answer.assert_called_with("✅ Накладная подтверждена")
        state.clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_review_callback_reject(self):
        """Test review callback with reject action"""
        # Create mock callback query
        callback = Mock(spec=types.CallbackQuery)
        callback.data = "reject_invoice"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=types.Message)
        callback.message.edit_text = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.clear = AsyncMock()
        
        # Call handler
        await handle_review_callback(callback, state)
        
        # Verify
        callback.answer.assert_called_with("❌ Накладная отклонена")
        state.clear.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.handlers.edit_flow.run_thread_safe')
    async def test_handle_free_edit_error_handling(
        self,
        mock_run_thread
    ):
        """Test error handling in free edit"""
        # Setup mock to raise exception
        mock_run_thread.side_effect = Exception("API Error")
        
        # Create mock message
        message = Mock(spec=types.Message)
        message.text = "строка 1 название Test"
        message.answer = AsyncMock()
        
        # Create mock state
        state = Mock(spec=FSMContext)
        state.get_data = AsyncMock(return_value={
            "invoice_data": {"positions": []},
            "match_results": []
        })
        
        # Call handler
        await handle_free_edit_input(message, state)
        
        # Verify error message
        message.answer.assert_called()
        call_args = message.answer.call_args[0][0]
        assert "Произошла ошибка" in call_args
    
    def test_router_filters(self):
        """Test that router has correct filters"""
        # Check that router has handlers registered
        handlers = router.message.handlers
        assert len(handlers) > 0
        
        # Check callback query handlers
        callback_handlers = router.callback_query.handlers
        assert len(callback_handlers) > 0
    
    @pytest.mark.asyncio
    @patch('app.handlers.edit_flow.build_report')
    async def test_update_report_after_edit(
        self,
        mock_build_report
    ):
        """Test report update after successful edit"""
        # Setup mocks
        mock_build_report.return_value = ("Updated report", False)
        
        # Create mock message
        message = Mock(spec=types.Message)
        message.bot = Mock()
        message.bot.edit_message_text = AsyncMock()
        
        # Create state data
        state_data = {
            "invoice_data": {"positions": [{"name": "Updated"}]},
            "match_results": [{"name": "Updated", "status": "ok"}],
            "report_message_id": 789,
            "chat_id": 456
        }
        
        # Test report update logic
        with patch('app.handlers.edit_flow.run_thread_safe') as mock_run:
            mock_run.return_value = [{"action": "set_name", "row": 1, "name": "Updated"}]
            
            with patch('app.handlers.edit_flow.apply_intent') as mock_apply:
                mock_apply.return_value = (
                    state_data["invoice_data"],
                    state_data["match_results"],
                    ["Applied"]
                )
                
                # Create handler context
                msg = Mock(spec=types.Message)
                msg.text = "строка 1 название Updated"
                msg.answer = AsyncMock()
                msg.bot = message.bot
                msg.chat = Mock(id=456)
                
                state = Mock(spec=FSMContext)
                state.get_data = AsyncMock(return_value=state_data)
                state.update_data = AsyncMock()
                state.clear = AsyncMock()
                
                await handle_free_edit_input(msg, state)
                
                mock_build_report.assert_called_once()


class TestEditFlowIntegration:
    """Integration tests for edit flow"""
    
    @pytest.mark.asyncio
    async def test_full_edit_flow(self):
        """Test complete edit flow from start to finish"""
        # This would test the full flow but requires more complex setup
        # with actual FSM context and message flow
        pass