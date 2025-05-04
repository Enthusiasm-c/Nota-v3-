import types
import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch
from bot import create_bot_and_dispatcher


@pytest.fixture
def fake_msg(monkeypatch):
    with patch("aiogram.Bot.__init__", return_value=None):
        bot, _ = create_bot_and_dispatcher()
    m = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="photo_id")], answer=AsyncMock()
    )
    monkeypatch.setattr(
        bot, "get_file", AsyncMock(return_value=types.SimpleNamespace(file_path="x"))
    )
    monkeypatch.setattr(
        bot,
        "download_file",
        AsyncMock(return_value=types.SimpleNamespace(getvalue=lambda: b"img")),
    )
    m.bot = bot
    return m
