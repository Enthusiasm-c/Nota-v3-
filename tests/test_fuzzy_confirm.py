import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
import bot
from app.fsm.states import EditFree


@pytest.mark.asyncio
async def test_handle_free_edit_text_fuzzy_suggestion():
    """Тест проверяет, что при редактировании имени с неточным совпадением 
    пользователю предлагается выбор имени с порогом 82%"""
    
    # Мокаем функцию fuzzy_process.extractOne для контроля результата
    with patch('rapidfuzz.process.extractOne') as mock_extract:
        # Настраиваем мок, чтобы он возвращал хорошее совпадение (score >= 82)
        mock_extract.return_value = ("Apple", 85)
        
        # Создаем мок сообщения
        message = AsyncMock()
        message.text = "строка 1 name aple"
        message.from_user = MagicMock(id=123)
        
        # Создаем мок объекта состояния
        state = AsyncMock(spec=FSMContext)
        state.get_data.return_value = {"edit_msg_id": 456}
        
        # Мокаем user_matches
        with patch.dict('bot.user_matches', {(123, 456): {
            "parsed_data": {
                "date": "2025-05-05",
                "supplier": "Test Supplier"
            },
            "match_results": [
                {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
            ]
        }}):
            # Мокаем data_loader.load_products
            with patch('app.data_loader.load_products') as mock_load:
                mock_load.return_value = [
                    MagicMock(name="Apple"),
                    MagicMock(name="Orange"),
                    MagicMock(name="Banana")
                ]
                
                # Вызываем функцию
                await bot.handle_free_edit_text(message, state)
                
                # Проверяем, что было предложено подтверждение
                message.answer.assert_called_once()
                args, kwargs = message.answer.call_args
                assert "Наверное, вы имели в виду" in args[0]
                assert "Apple" in args[0]
                
                # Проверяем, что в state сохранены нужные данные
                state.update_data.assert_called_once()
                _, kwargs = state.update_data.call_args
                assert "fuzzy_original" in kwargs
                assert kwargs["fuzzy_original"] == "aple"
                assert "fuzzy_match" in kwargs
                assert kwargs["fuzzy_match"] == "Apple"
                
                # Проверяем, что состояние изменено
                state.set_state.assert_called_once_with(EditFree.awaiting_free_edit)


@pytest.mark.asyncio
async def test_confirm_fuzzy_name():
    """Тест проверяет, что подтверждение fuzzy-совпадения корректно обрабатывается"""
    
    # Создаем мок callback
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "fuzzy:confirm:0"
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    
    # Создаем мок объекта состояния
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "fuzzy_original": "aple",
        "fuzzy_match": "Apple",
        "fuzzy_line": 0,
        "fuzzy_msg_id": 456
    }
    
    # Мокаем user_matches
    with patch.dict('bot.user_matches', {(123, 456): {
        "parsed_data": {
            "date": "2025-05-05",
            "supplier": "Test Supplier"
        },
        "match_results": [
            {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
        ]
    }}):
        # Мокаем data_loader.load_products
        with patch('app.data_loader.load_products') as mock_load:
            # Мокаем matcher.match_positions
            with patch('app.matcher.match_positions') as mock_match:
                mock_match.return_value = [
                    {"name": "Apple", "qty": 1, "unit": "kg", "price": 100, "status": "ok", "product_id": "apple001"}
                ]
                
                # Мокаем add_alias
                with patch('app.alias.add_alias') as mock_alias:
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


@pytest.mark.asyncio
async def test_reject_fuzzy_name():
    """Тест проверяет, что отклонение fuzzy-совпадения корректно обрабатывается"""
    
    # Создаем мок callback
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "fuzzy:reject:0"
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    
    # Создаем мок объекта состояния
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "fuzzy_original": "aple",
        "fuzzy_match": "Apple",
        "fuzzy_line": 0,
        "fuzzy_msg_id": 456
    }
    
    # Мокаем user_matches
    with patch.dict('bot.user_matches', {(123, 456): {
        "parsed_data": {
            "date": "2025-05-05",
            "supplier": "Test Supplier"
        },
        "match_results": [
            {"name": "Orange", "qty": 1, "unit": "kg", "price": 100, "status": "unknown"}
        ]
    }}):
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