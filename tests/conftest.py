import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.client.bot import Bot
from aiogram.types import Message


@pytest.fixture
def fake_msg(monkeypatch):
    # Создаем мок бота вместо использования настоящего
    mock_bot = MagicMock(spec=Bot)
    
    # Настраиваем необходимые методы мока
    mock_bot.get_file = AsyncMock(return_value=types.SimpleNamespace(file_path="test/file/path"))
    mock_bot.download_file = AsyncMock(return_value=types.SimpleNamespace(getvalue=lambda: b"test_image_bytes"))
    mock_bot.delete_message = AsyncMock(return_value=True)
    mock_bot.send_message = AsyncMock(return_value=types.SimpleNamespace(message_id=999))
    mock_bot.edit_message_text = AsyncMock(return_value=True)
    
    # Создаем объект сообщения с тестовыми данными
    msg = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="test_photo_id")], 
        answer=AsyncMock(return_value=types.SimpleNamespace(message_id=123)),
        bot=mock_bot
    )
    
    return msg
