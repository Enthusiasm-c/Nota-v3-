from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ParsedData, Position


def get_photo_handler(dp):
    # Ищем хендлер по имени callback (photo_handler)
    for handler in dp.message.handlers:
        if getattr(handler.callback, "__name__", "") == "photo_handler":
            return handler.callback
    return None


@pytest.mark.skip(reason="Тест требует дополнительной настройки и интеграции с IncrementalUI")
@pytest.mark.asyncio
async def test_photo_ok(monkeypatch, fake_msg):
    # Мокаем создание бота и диспетчера
    mock_bot = MagicMock()
    mock_dp = MagicMock()

    # Устанавливаем нужные методы и атрибуты для mock_bot
    mock_bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="x"))
    mock_bot.download_file = AsyncMock(return_value=SimpleNamespace(getvalue=lambda: b"img"))
    mock_bot.edit_message_text = AsyncMock(return_value=None)

    # Патчим функцию create_bot_and_dispatcher и глобальную переменную bot
    with patch("bot.create_bot_and_dispatcher", return_value=(mock_bot, mock_dp)), patch(
        "bot.bot", mock_bot
    ):
        # Импортируем после патча, чтобы использовать наш мок
        from bot import photo_handler, register_handlers

        register_handlers(mock_dp, mock_bot)

        # --- Добавляем недостающие атрибуты в fake_msg ---
        fake_msg.from_user = SimpleNamespace(id=42)  # Любой id пользователя
        fake_msg.message_id = 1  # Любой message_id
        fake_msg.chat = SimpleNamespace(id=123)  # Нужно для edit_message_text
        fake_msg.bot = mock_bot  # Привязываем наш мок бота к сообщению

        # --- Мокаем OCR и остальные функции ---
        monkeypatch.setattr(
            "app.ocr.call_openai_ocr",
            lambda *args, **kwargs: ParsedData(
                supplier="S", date=None, positions=[Position(name="A", qty=1, unit="kg")]
            ),
        )
        monkeypatch.setattr(
            "app.matcher.match_positions",
            lambda pos, prod=None: [
                {"name": "A", "qty": 1, "unit": "kg", "price": 10, "status": "ok"},
                {"name": "B", "qty": 2, "unit": "l", "price": 20, "status": "ok"},
            ],
        )

        def fake_build_report(*args, **kwargs):
            return "Report content", False

        monkeypatch.setattr("app.formatters.report.build_report", fake_build_report)
        monkeypatch.setattr("bot.safe_edit", AsyncMock(return_value=None))

        # Создаем фейковый state для передачи в photo_handler
        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={"lang": "ru"})
        mock_state.update_data = AsyncMock()
        mock_state.set_state = AsyncMock()

        # Определяем прогресс функцию, которая ожидается в kwargs
        async def update_progress_message(stage=None, stage_name=None, error_message=None):
            pass

        # Вызываем обработчик с нужными аргументами
        kwargs = {
            "_stages": {},
            "_stages_names": {},
            "_req_id": "test123",
            "_update_progress": update_progress_message,
        }

        await photo_handler(fake_msg, mock_state, **kwargs)

        assert fake_msg.answer.call_count >= 1

        # Проверяем, что было вызвано обновление UI или отправлено сообщение с отчетом
        answers = fake_msg.answer.call_args_list
        found_report = False
        for call in answers:
            if len(call[0]) > 0 and isinstance(call[0][0], str) and "Report content" in call[0][0]:
                found_report = True
                break

        assert (
            found_report
        ), f"Expected report in answer calls, got: {[c[0][0] if len(c[0])>0 else None for c in answers]}"


@pytest.mark.skip(reason="Тест требует дополнительной настройки и интеграции с IncrementalUI")
@pytest.mark.asyncio
async def test_photo_error(monkeypatch, fake_msg):
    # Мокаем создание бота и диспетчера
    mock_bot = MagicMock()
    mock_dp = MagicMock()

    # Устанавливаем нужные методы и атрибуты для mock_bot
    mock_bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="x"))
    mock_bot.download_file = AsyncMock(return_value=SimpleNamespace(getvalue=lambda: b"img"))
    mock_bot.edit_message_text = AsyncMock(return_value=None)
    mock_bot.delete_message = AsyncMock(return_value=None)

    # Патчим функцию create_bot_and_dispatcher и глобальную переменную bot
    with patch("bot.create_bot_and_dispatcher", return_value=(mock_bot, mock_dp)), patch(
        "bot.bot", mock_bot
    ):
        # Импортируем после патча, чтобы использовать наш мок
        from bot import photo_handler, register_handlers

        register_handlers(mock_dp, mock_bot)

        # --- Добавляем недостающие атрибуты в fake_msg ---
        fake_msg.from_user = SimpleNamespace(id=42)
        fake_msg.message_id = 1
        fake_msg.chat = SimpleNamespace(id=123)
        fake_msg.bot = mock_bot

        # --- Мокаем OCR с выбрасыванием ошибки ---
        def raise_error(*args, **kwargs):
            raise Exception("OCR failed")

        monkeypatch.setattr("app.ocr.call_openai_ocr", raise_error)
        monkeypatch.setattr("bot.safe_edit", AsyncMock(return_value=None))

        # Создаем фейковый state для передачи в photo_handler
        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={"lang": "ru"})
        mock_state.update_data = AsyncMock()
        mock_state.set_state = AsyncMock()

        # Определяем прогресс функцию, которая ожидается в kwargs
        async def update_progress_message(stage=None, stage_name=None, error_message=None):
            pass

        # Вызываем обработчик с нужными аргументами
        kwargs = {
            "_stages": {},
            "_stages_names": {},
            "_req_id": "test123",
            "_update_progress": update_progress_message,
        }

        await photo_handler(fake_msg, mock_state, **kwargs)

        assert fake_msg.answer.call_count >= 1
        calls = fake_msg.answer.call_args_list

        # Ищем сообщение об ошибке
        found_error = False
        for call in calls:
            if (
                len(call[0]) > 0
                and isinstance(call[0][0], str)
                and "OCR" in call[0][0]
                and "failed" in call[0][0].lower()
            ):
                found_error = True
                break

        assert (
            found_error
        ), f"Expected OCR error in answer, got: {[c[0][0] if len(c[0])>0 else None for c in calls]}"


# --- Добавляем перевод строки в конец файла ---
