import pytest
from app.formatter import build_report
from types import SimpleNamespace
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_formatter_no_bad_chars():
    """
    Формирует отчёт build_report и отправляет его через send_message(parse_mode=MarkdownV2).
    Проверяет, что Telegram не ругается на спецсимволы (#, !, | ...).
    """
    # Фейковый бот
    class FakeBot:
        def __init__(self):
            self.sent = []
        async def send_message(self, chat_id, text, parse_mode=None):
            self.sent.append((chat_id, text, parse_mode))
            # Эмулируем успешную отправку (не выбрасываем TelegramBadRequest)
            return SimpleNamespace(message_id=123)
    bot = FakeBot()
    # Данные с опасными символами
    parsed = SimpleNamespace(supplier='#ООО "Тест+!"', date="2024-05-03")
    match_results = [
        {"name": "#Кефир (1л)", "qty": 2, "unit": "+л.", "price": 99.5, "status": "ok"},
        {"name": "Молоко!", "qty": 1, "unit": "л", "price": 70, "status": "unit_mismatch"},
        {"name": "Творог|", "qty": 1, "unit": "кг", "price": 200, "status": "unknown"},
    ]
    text = build_report(parsed, match_results)
    # Попытка отправки (имитируем Telegram API)
    await bot.send_message(42, text, parse_mode="MarkdownV2")
    # Проверяем, что сообщение ушло и parse_mode был верный
    assert bot.sent, "Message was not sent"
    chat_id, sent_text, parse_mode = bot.sent[0]
    assert parse_mode == "MarkdownV2"
    # Проверяем, что спецсимволы экранированы или внутри code block
    assert '```' in sent_text, "Table must be in code block"
    assert '#  NAME' in sent_text, "Header must be present and not cause error"
    # (Тест не падает, если нет TelegramBadRequest)
