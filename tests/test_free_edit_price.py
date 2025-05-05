import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree

@pytest.mark.asyncio
async def test_free_edit_price():
    """
    Тест проверяет редактирование цены через GPT-ассистент.
    
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
    
    # Мок для OpenAI Assistant
    assistant_response = {
        "action": "set_price",
        "line_index": 1,  # 0-based index для второй строки
        "value": "95000"
    }
    
    # Мокаем app.edit.apply_intent.apply_intent напрямую, чтобы не обращаться к OpenAI
    with patch('app.handlers.edit_flow.run_thread_safe', side_effect=lambda x: assistant_response):
            # Мокаем app.edit.apply_intent.set_price
            with patch('app.edit.apply_intent.set_price') as mock_set_price:
                # Имитируем функцию set_price
                def side_effect(invoice, line_index, value):
                    invoice["positions"][line_index]["price"] = value
                    invoice["positions"][line_index]["status"] = "ok"  # Статус меняется на ок
                    return invoice
                
                mock_set_price.side_effect = side_effect
                
                # Мокаем обновление issues_count
                with patch('app.formatters.report.count_issues', return_value=1):
                    # Мокаем formatters.report.build_report
                    with patch('app.formatters.report.build_report') as mock_build_report:
                        mock_build_report.return_value = ("<html>Updated invoice</html>", False)
                        
                        # Мокаем клавиатуру
                        with patch('app.keyboards.build_main_kb') as mock_build_kb:
                            # Вызываем тестируемую функцию
                            from app.handlers.edit_flow import handle_free_edit_text
                            await handle_free_edit_text(message, state)
                            
                            # Проверки
                            
                            # 1. Проверяем, что OpenAI Assistant был вызван с правильным текстом
                            from app.assistants.client import run_thread_safe
                            run_thread_safe.assert_called_once_with(message.text)
                            
                            # 2. Проверяем, что set_price был вызван с правильными параметрами
                            mock_set_price.assert_called_once()
                            args, _ = mock_set_price.call_args
                            assert args[1] == 1  # line_index
                            assert args[2] == "95000"  # value
                            
                            # 3. Проверяем, что цена изменилась в invoice
                            updated_data = {}
                            for call in state.update_data.call_args_list:
                                updated_data.update(call[0][0])
                            
                            assert updated_data["invoice"]["positions"][1]["price"] == "95000"
                            assert updated_data["invoice"]["positions"][1]["status"] == "ok"
                            
                            # 4. Проверяем, что issues_count уменьшилось
                            assert updated_data["issues_count"] == 1
                            
                            # 5. Проверяем, что отчёт был пересобран
                            mock_build_report.assert_called_once()
                            
                            # 6. Проверяем, что сообщение было отправлено с HTML-форматированием
                            message.answer.assert_called_once()
                            _, kwargs = message.answer.call_args
                            assert kwargs.get('parse_mode') == "HTML"