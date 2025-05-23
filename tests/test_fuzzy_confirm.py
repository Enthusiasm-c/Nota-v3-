from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import bot
from app.fsm.states import EditFree


@pytest.mark.asyncio
async def test_handle_free_edit_text_fuzzy_suggestion():
    """Тест проверяет, что при редактировании имени с неточным совпадением
    пользователю предлагается выбор имени с порогом 82%"""

    # Мокаем функцию fuzzy_process.extractOne для контроля результата
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        # Настраиваем мок, чтобы он возвращал хорошее совпадение (score >= 82)
        mock_extract.return_value = ("Apple", 85)

        # Создаем мок сообщения
        message = AsyncMock()
        message.text = "строка 1 name aple"
        message.from_user = MagicMock(id=123)

        # Создаем мок объекта состояния
        state = AsyncMock(spec=FSMContext)
        # Добавляем ключ 'invoice', чтобы не было преждевременного завершения сессии
        state.get_data.return_value = {
            "edit_msg_id": 456,
            "invoice": {
                "positions": [
                    {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
                ],
                "date": "2025-05-05",
                "supplier": "Test Supplier",
            },
        }

        # Мокаем user_matches
        with patch.dict(
            "bot.user_matches",
            {
                (123, 456): {
                    "parsed_data": {"date": "2025-05-05", "supplier": "Test Supplier"},
                    "match_results": [
                        {
                            "name": "Orange",
                            "qty": 1,
                            "unit": "kg",
                            "price": 100,
                            "status": "unknown",
                        }
                    ],
                }
            },
        ):
            # Мокаем переменную ASSISTANT_ID, чтобы избежать ошибки assistant_not_configured
            with patch("app.assistants.client.ASSISTANT_ID", "dummy_id"):
                # Мокаем функцию разбора команды assistant, чтобы не зависеть от OpenAI
                with patch("app.handlers.edit_flow.run_thread_safe") as mock_assist:
                    mock_assist.return_value = {"action": "edit_name", "line": 0, "value": "aple"}
                    # Мокаем data_loader.load_products
                    with patch("app.data_loader.load_products") as mock_load:
                        mock_load.return_value = [
                            MagicMock(name="Apple"),
                            MagicMock(name="Orange"),
                            MagicMock(name="Banana"),
                        ]

                        # Вызываем функцию
                        await bot.handle_free_edit_text(message, state)

                        # Проверяем, что среди всех вызовов message.answer есть подсказка
                        answer_calls = [call[0][0] for call in message.answer.call_args_list]
                        assert any(
                            "Наверное, вы имели в виду" in text and "Apple" in text
                            for text in answer_calls
                        )

                        # Проверяем, что среди всех вызовов update_data был вызов с fuzzy_original и fuzzy_match
                        update_calls = state.update_data.call_args_list
                        assert any(
                            "fuzzy_original" in call.kwargs
                            and call.kwargs["fuzzy_original"] == "aple"
                            and "fuzzy_match" in call.kwargs
                            and call.kwargs["fuzzy_match"] == "Apple"
                            for call in update_calls
                        )

                        # Проверяем, что состояние изменено на ожидание ввода
                        setstate_calls = [call.args[0] for call in state.set_state.call_args_list]
                        assert EditFree.awaiting_input in setstate_calls
                # Проверяем, что в state сохранены нужные данные

                # Проверяем, что состояние изменено
                state.set_state.assert_called_once_with(EditFree.awaiting_input)


@pytest.mark.asyncio
async def test_confirm_fuzzy_name():
    """Тест проверяет, что подтверждение fuzzy-совпадения корректно обрабатывается"""

    # Создаем мок callback
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "fuzzy:confirm:0"
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    # Используем AsyncMock для callback.answer, чтобы можно было await
    callback.answer = AsyncMock()

    # Создаем мок объекта состояния
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "fuzzy_original": "aple",
        "fuzzy_match": "Apple",
        "fuzzy_line": 0,
        "fuzzy_msg_id": 456,
    }

    # Мокаем user_matches
    with patch.dict(
        "bot.user_matches",
        {
            (123, 456): {
                "parsed_data": {"date": "2025-05-05", "supplier": "Test Supplier"},
                "match_results": [
                    {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
                ],
            }
        },
    ):
        # Мокаем data_loader.load_products
        with patch("app.data_loader.load_products") as mock_load:
            mock_load.return_value = [
                MagicMock(name="Apple"),
                MagicMock(name="Orange"),
                MagicMock(name="Banana"),
            ]
            # Мокаем matcher.match_positions
            with patch("app.matcher.match_positions") as mock_match:
                mock_match.return_value = [
                    {
                        "name": "Apple",
                        "qty": 1,
                        "unit": "kg",
                        "price": 100,
                        "status": "ok",
                        "product_id": "apple001",
                    }
                ]

                # Мокаем add_alias
                with patch("app.alias.add_alias") as mock_alias:
                    # Вызываем функцию
                    await bot.confirm_fuzzy_name(callback, state)

                    # Проверяем, что был вызван add_alias
                    mock_alias.assert_called_once_with("aple", "apple001")

                    # Проверяем, что было создано сообщение с отчетом
                    callback.message.answer.assert_called_once()

                    # Проверяем, что клавиатура с кнопками подтверждения была удалена
                    callback.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

                    # Проверяем, что состояние изменено
                    state.set_state.assert_called_once_with(bot.NotaStates.editing)

                    # Проверяем, что load_products был вызван
                    mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_reject_fuzzy_name():
    """Тест проверяет, что отклонение fuzzy-совпадения корректно обрабатывается"""

    # Создаем мок callback
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "fuzzy:reject:0"
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    # Используем AsyncMock для callback.answer, чтобы можно было await
    callback.answer = AsyncMock()

    # Создаем мок объекта состояния
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "fuzzy_original": "aple",
        "fuzzy_match": "Apple",
        "fuzzy_line": 0,
        "fuzzy_msg_id": 456,
    }

    # Мокаем user_matches
    with patch.dict(
        "bot.user_matches",
        {
            (123, 456): {
                "parsed_data": {"date": "2025-05-05", "supplier": "Test Supplier"},
                "match_results": [
                    {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
                ],
            }
        },
    ):
        # Вызываем функцию
        await bot.reject_fuzzy_name(callback, state)

        # Проверяем, что имя позиции было установлено в оригинальное значение
        assert bot.user_matches[(123, 456)]["match_results"][0]["name"] == "aple"

        # Проверяем, что статус позиции изменен на "unknown"
        assert bot.user_matches[(123, 456)]["match_results"][0]["status"] == "unknown"

        # Проверяем, что было создано сообщение с отчетом
        callback.message.answer.assert_called_once()

        # Проверяем, что клавиатура с кнопками подтверждения была удалена
        callback.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

        # Проверяем, что состояние изменено
        state.set_state.assert_called_once_with(bot.NotaStates.editing)
