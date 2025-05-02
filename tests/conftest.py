import types
import pytest
from unittest.mock import AsyncMock
from bot import bot

@pytest.fixture
def fake_msg(monkeypatch):
    m = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="photo_id")],
        answer=AsyncMock()
    )
    monkeypatch.setattr(bot, "get_file", AsyncMock(
        return_value=types.SimpleNamespace(file_path="x")))
    monkeypatch.setattr(bot, "download_file",
                        AsyncMock(return_value=types.SimpleNamespace(getvalue=lambda: b"img")))
    return m
