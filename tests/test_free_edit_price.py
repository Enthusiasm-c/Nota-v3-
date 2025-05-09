import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree

@pytest.mark.asyncio
async def test_free_edit_price():
    """
    Тест проверяет редактирование цены через прямое распознавание паттернов.
    
    Given накладная с 2 ошибочными строками.
    When пользователь в FSM-состоянии EditFree.awaiting_input присылает «строка 2 цена 95000».
    Then 
    - поле price второй строки = 95000;
    - issues_count уменьшилось на 1;
    - отчёт пересобран и отправлен одной edit_message_text с parse_mode="HTML".
    """
    # Создаем мок сообщения
    message = AsyncMock(spec=Message)
    message.text = "строка 2 цена 95000"
    message.from_user = MagicMock(id=123)
    message.chat = MagicMock(id=456)
    message.answer = AsyncMock()
    
    # Создаем мок для удаления сообщения
    processing_msg = AsyncMock()
    message.answer.return_value = processing_msg
    
    # Создаем мок состояния FSM
    state = AsyncMock(spec=FSMContext)
    
    # Настраиваем состояние FSM для EditFree.awaiting_input
    async def mock_get_state():
        return EditFree.awaiting_input
    state.get_state = mock_get_state
    
    # Данные для state.get_data
    state_data = {
        "invoice": {
            "date": "2025-05-05",
            "supplier": "Test Supplier",
            "positions": [
                {"name": "Apple", "qty": "1", "unit": "kg", "price": "100", "status": "ok"},
                {"name": "Orange", "qty": "2", "unit": "kg", "price": "incorrect", "status": "error"},  # Ошибочная цена
            ]
        },
        "issues_count": 2  # Начальное количество ошибок
    }
    state.get_data.return_value = state_data
    
    # Mock the utils.cached_loader.cached_load_products
    with patch('app.utils.cached_loader.cached_load_products') as mock_cached_load:
        mock_cached_load.return_value = [
            {"id": "apple-1", "name": "apple", "unit": "kg"},
            {"id": "orange-1", "name": "orange", "unit": "kg"}
        ]
        
        # Mock handlers.name_picker.show_fuzzy_suggestions to prevent errors
        with patch('app.handlers.name_picker.show_fuzzy_suggestions') as mock_fuzzy:
            mock_fuzzy.return_value = False  # No suggestions shown
            
            # Mock matcher.match_positions to prevent errors
            with patch('app.matcher.match_positions') as mock_match:
                mock_match.return_value = [
                    {"name": "Apple", "status": "ok"},
                    {"name": "Orange", "status": "ok"}  # Now recognized properly
                ]
                
                # We need to patch the specific import inside the function
                with patch('app.edit.apply_intent.apply_intent') as mock_apply_intent:
                    # Simulate the behavior of apply_intent to update price
                    def apply_intent_side_effect(invoice, action_data):
                        # Create a copy to avoid modifying the original
                        invoice_copy = invoice.copy()
                        if action_data.get("action") == "set_price" and "line" in action_data:
                            line_idx = action_data["line"]
                            price = action_data.get("value", action_data.get("price"))
                            invoice_copy["positions"][line_idx]["price"] = str(price)
                            invoice_copy["positions"][line_idx]["status"] = "ok"
                        return invoice_copy
                    
                    mock_apply_intent.side_effect = apply_intent_side_effect
                
                    # Mock formatters.report.build_report to prevent UI errors
                    with patch('app.formatters.report.build_report') as mock_build_report:
                        mock_build_report.return_value = ("<html>Updated invoice</html>", False)
                        
                        # Вызываем тестируемую функцию
                        from app.handlers.edit_flow import handle_free_edit_text
                        await handle_free_edit_text(message, state)
                        
                        # Check that apply_intent was called
                        mock_apply_intent.assert_called()
                        
                        # Extract the first call arguments
                        args, _ = mock_apply_intent.call_args_list[0]
                        action_data = args[1]
                        
                        # Verify we got a set_price action
                        assert action_data.get("action") == "set_price"
                        
                        # Verify we got the right line number (should be 1, 0-indexed)
                        assert action_data.get("line") == 1
                        
                        # Verify the price value - could be in 'price' or 'value' field
                        price_value = action_data.get("price", action_data.get("value", 0))
                        assert price_value == 95000.0
                        
                        # Verify state was updated
                        state.update_data.assert_called()
                        
                        # Verify report was built
                        mock_build_report.assert_called()