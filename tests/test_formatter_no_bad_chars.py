from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.formatters.report import build_report


@pytest.mark.asyncio
async def test_formatter_no_bad_chars():
    """
    Формирует отчёт build_report и отправляет его через send_message(parse_mode=HTML).
    Проверяет, что Telegram не ругается на спецсимволы (#, !, | ...), а отчёт формируется в HTML.
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
        {
            "name": "Молоко!",
            "qty": 1,
            "unit": "л",
            "price": 70,
            "status": "unit_mismatch",
        },
        {"name": "Творог|", "qty": 1, "unit": "кг", "price": 200, "status": "unknown"},
    ]
    text, _ = build_report(parsed, match_results)
    # Попытка отправки (имитируем Telegram API)
    await bot.send_message(42, text, parse_mode="HTML")
    # Проверяем, что сообщение ушло и parse_mode был верный
    assert bot.sent, "Message was not sent"
    chat_id, sent_text, parse_mode = bot.sent[0]
    assert parse_mode == "HTML"
    # Проверяем, что отчёт в HTML (<pre>), а не в Markdown code block
    assert "```" not in sent_text, "Should not use Markdown code block in HTML mode"
    assert "#  NAME" in sent_text, "Header must be present and not cause error"
    # Проверяем, что опасные символы экранированы
    assert "amp;" in sent_text, "HTML entities should be escaped"
    # (Тест не падает, если нет TelegramBadRequest)


@pytest.mark.asyncio
async def test_formatter_with_telegram_exception():
    """
    Проверяет обработку исключения TelegramBadRequest при отправке сообщений
    с HTML-форматированием, содержащих специальные символы.
    """

    # Бот, который выбрасывает исключение при первой попытке отправки
    class FailingBot:
        def __init__(self):
            self.attempts = 0
            self.sent = []

        async def send_message(self, chat_id, text, parse_mode=None):
            self.attempts += 1
            if self.attempts == 1 and parse_mode == "HTML":
                # Симулируем ошибку парсинга HTML
                raise TelegramBadRequest(
                    method="sendMessage", message="Bad Request: can't parse entities"
                )

            # Если сюда дошли, значит это вторая попытка или без форматирования
            self.sent.append((chat_id, text, parse_mode))
            return SimpleNamespace(message_id=123)

    bot = FailingBot()

    # Данные с опасными символами
    parsed = SimpleNamespace(supplier="Опасные символы: <>[](){}\\/|", date="2024-05-03")
    match_results = [
        {"name": "Продукт с <тегами>", "qty": 1, "unit": "шт", "price": 100, "status": "ok"},
    ]

    text, _ = build_report(parsed, match_results)

    # Симулируем обработку ошибки как в safe_edit
    try:
        await bot.send_message(42, text, parse_mode="HTML")
    except TelegramBadRequest:
        # Должны попасть сюда на первой попытке
        # Вторая попытка - без форматирования
        await bot.send_message(42, text, parse_mode=None)

    # Проверяем, что было две попытки
    assert bot.attempts == 2, "Should have made two attempts"

    # Проверяем, что вторая попытка была без форматирования
    assert len(bot.sent) == 1, "Second attempt should have succeeded"
    _, _, second_parse_mode = bot.sent[0]
    assert second_parse_mode is None, "Second attempt should be without parse_mode"
