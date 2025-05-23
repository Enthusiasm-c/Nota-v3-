from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.fsm.states import EditFree


@pytest.mark.asyncio
async def test_free_edit_date():
    """
    Тест проверяет редактирование даты через GPT-ассистент.

    Given дата пустая.
    When сообщение: «дата 16 апреля».
    Then дата = 2025-04-16, отчёт перегенерирован, клавиатура не содержит ✅.
    """
    # Создаем мок сообщения
    message = AsyncMock(spec=Message)
    message.text = "дата 16 апреля"
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
            "date": "",  # Пустая дата
            "supplier": "Test Supplier",
            "positions": [
                {"name": "Apple", "qty": "1", "unit": "kg", "price": "100", "status": "ok"},
                {"name": "Orange", "qty": "2", "unit": "kg", "price": "200", "status": "ok"},
            ],
        },
        "issues_count": 1,  # Начальное количество ошибок (из-за пустой даты)
    }
    state.get_data.return_value = state_data

    # Мок для OpenAI Assistant
    assistant_response = {"action": "set_date", "value": "2025-04-16"}

    # Мокаем ASSISTANT_ID чтобы не было ошибки
    with patch("app.assistants.client.ASSISTANT_ID", "test-assistant-id"):
        # Мокаем app.assistants.client.run_thread_safe, чтобы не обращался к OpenAI
        with patch(
            "app.assistants.client.run_thread_safe", side_effect=lambda x: assistant_response
        ):
            # Мокаем app.edit.apply_intent.set_date
            with patch("app.edit.apply_intent.set_date") as mock_set_date:
                # Имитируем функцию set_date
                def side_effect(invoice, value):
                    invoice["date"] = value
                    return invoice

                mock_set_date.side_effect = side_effect

                # Мокаем обновление issues_count
                with patch("app.formatters.report.count_issues", return_value=0):
                    # Мокаем formatters.report.build_report
                    with patch("app.formatters.report.build_report") as mock_build_report:
                        # В отчете все еще есть ошибки (has_errors=True)
                        mock_build_report.return_value = (
                            "<html>Updated invoice with date</html>",
                            True,
                        )

                        # Мокаем клавиатуру
                        with patch("app.keyboards.build_main_kb") as mock_build_kb:
                            # Вызываем тестируемую функцию
                            from app.handlers.edit_flow import handle_free_edit_text

                            await handle_free_edit_text(message, state)

                            # Проверки

                            # 1. Проверяем, что OpenAI Assistant был вызван с правильным текстом
                            from app.assistants.client import run_thread_safe

                            run_thread_safe.assert_called_once_with(message.text)

                            # 2. Проверяем, что set_date был вызван с правильными параметрами
                            mock_set_date.assert_called_once()
                            args, _ = mock_set_date.call_args
                            assert args[1] == "2025-04-16"  # value

                            # 3. Проверяем, что дата изменилась в invoice
                            updated_data = {}
                            for call in state.update_data.call_args_list:
                                updated_data.update(call[0][0])

                            assert updated_data["invoice"]["date"] == "2025-04-16"

                            # 4. Проверяем, что отчёт был пересобран
                            mock_build_report.assert_called_once()

                            # 5. Проверяем, что сообщение было отправлено с HTML-форматированием
                            message.answer.assert_called_once()
                            _, kwargs = message.answer.call_args
                            assert kwargs.get("parse_mode") == "HTML"

                            # 6. Проверяем, что клавиатура была вызвана с has_errors=True (нет кнопки ✅)
                            mock_build_kb.assert_called_once_with(True)
