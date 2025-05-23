"""
Тесты для модуля app/utils/async_ocr.py
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.models import ParsedData, Position
from app.utils.async_ocr import (
    DEFAULT_TIMEOUT,
    INVOICE_FUNCTION_SCHEMA,
    async_ocr,
    close_http_session,
    get_http_session,
)


class TestAsyncOCRConfig:
    """Тесты конфигурации модуля"""

    def test_default_timeout_configuration(self):
        """Тест настройки таймаута по умолчанию"""
        assert DEFAULT_TIMEOUT.total == 30

    def test_invoice_function_schema_structure(self):
        """Тест корректности схемы функции инвойса"""
        assert INVOICE_FUNCTION_SCHEMA["name"] == "get_parsed_invoice"
        assert "parameters" in INVOICE_FUNCTION_SCHEMA
        assert INVOICE_FUNCTION_SCHEMA["parameters"]["type"] == "object"

        properties = INVOICE_FUNCTION_SCHEMA["parameters"]["properties"]
        assert "supplier" in properties
        assert "positions" in properties
        assert properties["positions"]["type"] == "array"


class TestHTTPSession:
    """Тесты управления HTTP сессией"""

    @pytest.mark.asyncio
    async def test_get_http_session_creates_session(self):
        """Тест создания новой HTTP сессии"""
        # Закрываем существующую сессию
        await close_http_session()

        session = await get_http_session()
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed

        # Очистка
        await close_http_session()

    @pytest.mark.asyncio
    async def test_get_http_session_reuses_existing(self):
        """Тест повторного использования существующей сессии"""
        await close_http_session()

        session1 = await get_http_session()
        session2 = await get_http_session()

        assert session1 is session2
        assert not session1.closed

        await close_http_session()

    @pytest.mark.asyncio
    async def test_get_http_session_recreates_closed_session(self):
        """Тест пересоздания закрытой сессии"""
        await close_http_session()

        session1 = await get_http_session()
        await session1.close()

        session2 = await get_http_session()
        assert session1 is not session2
        assert not session2.closed

        await close_http_session()

    @pytest.mark.asyncio
    async def test_close_http_session_no_session(self):
        """Тест закрытия когда сессии нет"""
        await close_http_session()
        # Не должно быть исключений
        await close_http_session()

    @pytest.mark.asyncio
    async def test_close_http_session_already_closed(self):
        """Тест закрытия уже закрытой сессии"""
        session = await get_http_session()
        await session.close()

        # Не должно быть исключений
        await close_http_session()


class TestAsyncOCR:
    """Тесты основной функции async_ocr"""

    @pytest.fixture
    def sample_image_bytes(self):
        """Образец байтов изображения"""
        return b"fake_image_data"

    @pytest.fixture
    def mock_api_response(self):
        """Мок ответа API OpenAI"""
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_parsed_invoice",
                                    "arguments": json.dumps(
                                        {
                                            "supplier": "Тестовый поставщик",
                                            "date": "2024-01-15",
                                            "positions": [
                                                {
                                                    "name": "Хлеб",
                                                    "qty": 10,
                                                    "unit": "шт",
                                                    "price": 50.0,
                                                    "total_price": 500.0,
                                                }
                                            ],
                                            "total_price": 500.0,
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_async_ocr_success(self, sample_image_bytes, mock_api_response):
        """Тест успешного выполнения OCR"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.async_store_in_cache", new_callable=AsyncMock
        ), patch("app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            # Мокируем ParsedData.model_validate
            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик",
                date="2024-01-15",
                positions=[Position(name="Хлеб", qty=10, unit="шт", price=50.0, total_price=500.0)],
                total_price=500.0,
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                # Мокируем HTTP запрос
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                # Создаем правильный контекст менеджер
                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    result = await async_ocr(sample_image_bytes, req_id="test_123")

                    assert result == expected_parsed_data
                    mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_ocr_cache_hit(self, sample_image_bytes):
        """Тест использования кешированного результата"""
        cached_data = ParsedData(
            supplier="Кешированный поставщик",
            positions=[Position(name="Кешированный продукт", qty=1)],
        )

        with patch("app.utils.async_ocr.async_get_from_cache", return_value=cached_data):
            result = await async_ocr(sample_image_bytes, use_cache=True)
            assert result == cached_data

    @pytest.mark.asyncio
    async def test_async_ocr_cache_disabled(self, sample_image_bytes, mock_api_response):
        """Тест работы без кеша"""
        with patch("app.utils.async_ocr.async_get_from_cache") as mock_cache_get, patch(
            "app.utils.async_ocr.async_store_in_cache"
        ) as mock_cache_store, patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    await async_ocr(sample_image_bytes, use_cache=False)

                    # Кеш не должен использоваться
                    mock_cache_get.assert_not_called()
                    mock_cache_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_ocr_cache_read_error(self, sample_image_bytes, mock_api_response):
        """Тест обработки ошибки чтения кеша"""
        with patch(
            "app.utils.async_ocr.async_get_from_cache", side_effect=Exception("Ошибка кеша")
        ), patch("app.utils.async_ocr.async_store_in_cache", new_callable=AsyncMock), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    # Должно продолжить работу несмотря на ошибку кеша
                    result = await async_ocr(sample_image_bytes)
                    assert result == expected_parsed_data

    @pytest.mark.asyncio
    async def test_async_ocr_image_optimization_error(self, sample_image_bytes, mock_api_response):
        """Тест обработки ошибки оптимизации изображения"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", side_effect=Exception("Ошибка оптимизации")
        ), patch("app.utils.async_ocr.postprocess_parsed_data") as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    # Должно использовать оригинальное изображение
                    result = await async_ocr(sample_image_bytes)
                    assert result == expected_parsed_data

    @pytest.mark.asyncio
    async def test_async_ocr_no_api_key(self, sample_image_bytes):
        """Тест ошибки отсутствия API ключа"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = ""

            # Удаляем OPENAI_API_KEY если есть
            if hasattr(mock_settings, "OPENAI_API_KEY"):
                delattr(mock_settings, "OPENAI_API_KEY")

            with pytest.raises(RuntimeError, match="Нет доступного API ключа для OCR"):
                await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_fallback_api_key(self, sample_image_bytes, mock_api_response):
        """Тест использования резервного API ключа"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.postprocess_parsed_data") as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = ""
            mock_settings.OPENAI_API_KEY = "fallback_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    result = await async_ocr(sample_image_bytes)
                    assert result == expected_parsed_data

    @pytest.mark.asyncio
    async def test_async_ocr_api_error_status(self, sample_image_bytes):
        """Тест обработки ошибки статуса API"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")

            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.return_value = async_context_manager
                mock_get_session.return_value = mock_session

                with pytest.raises(RuntimeError, match="OCR API вернул ошибку: 500"):
                    await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_timeout(self, sample_image_bytes):
        """Тест таймаута OCR"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.side_effect = asyncio.TimeoutError("Timeout")
                mock_get_session.return_value = mock_session

                with pytest.raises(asyncio.TimeoutError, match="OCR операция превысила таймаут"):
                    await async_ocr(sample_image_bytes, timeout=1)

    @pytest.mark.asyncio
    async def test_async_ocr_empty_response(self, sample_image_bytes):
        """Тест пустого ответа API"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"choices": []})

            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.return_value = async_context_manager
                mock_get_session.return_value = mock_session

                with pytest.raises(ValueError, match="Пустой ответ от OpenAI API"):
                    await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_no_tool_calls(self, sample_image_bytes):
        """Тест ответа без tool_calls"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"choices": [{"message": {"content": "Обычный ответ без tool_calls"}}]}
            )

            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.return_value = async_context_manager
                mock_get_session.return_value = mock_session

                with pytest.raises(ValueError, match="Ответ не содержит результат функции"):
                    await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_wrong_function_name(self, sample_image_bytes):
        """Тест неправильного имени функции"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {"function": {"name": "wrong_function", "arguments": "{}"}}
                                ]
                            }
                        }
                    ]
                }
            )

            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.return_value = async_context_manager
                mock_get_session.return_value = mock_session

                with pytest.raises(ValueError, match="Неожиданное имя функции: wrong_function"):
                    await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_invalid_json(self, sample_image_bytes):
        """Тест невалидного JSON в аргументах функции"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes
        ), patch("app.utils.async_ocr.settings") as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "get_parsed_invoice",
                                            "arguments": "invalid json",
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)

            with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                mock_session = AsyncMock()
                mock_session.post.return_value = async_context_manager
                mock_get_session.return_value = mock_session

                with pytest.raises(RuntimeError):
                    await async_ocr(sample_image_bytes)

    @pytest.mark.asyncio
    async def test_async_ocr_cache_store_error(self, sample_image_bytes, mock_api_response):
        """Тест ошибки записи в кеш"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.async_store_in_cache", side_effect=Exception("Ошибка записи кеша")
        ), patch("app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    # Должно работать несмотря на ошибку кеширования
                    result = await async_ocr(sample_image_bytes)
                    assert result == expected_parsed_data

    @pytest.mark.asyncio
    async def test_async_ocr_custom_req_id(self, sample_image_bytes, mock_api_response):
        """Тест использования пользовательского req_id"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.async_store_in_cache", new_callable=AsyncMock
        ), patch("app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    result = await async_ocr(sample_image_bytes, req_id="custom_123")
                    assert result == expected_parsed_data

    @pytest.mark.asyncio
    async def test_async_ocr_custom_timeout(self, sample_image_bytes, mock_api_response):
        """Тест использования пользовательского таймаута"""
        with patch("app.utils.async_ocr.async_get_from_cache", return_value=None), patch(
            "app.utils.async_ocr.async_store_in_cache", new_callable=AsyncMock
        ), patch("app.utils.async_ocr.prepare_for_ocr", return_value=sample_image_bytes), patch(
            "app.utils.async_ocr.postprocess_parsed_data"
        ) as mock_postprocess, patch(
            "app.utils.async_ocr.settings"
        ) as mock_settings:

            mock_settings.OPENAI_OCR_KEY = "test_key"

            expected_parsed_data = ParsedData(
                supplier="Тестовый поставщик", positions=[Position(name="Хлеб", qty=10)]
            )
            mock_postprocess.return_value = expected_parsed_data

            with patch("app.models.ParsedData.model_validate", return_value=expected_parsed_data):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_api_response)

                async_context_manager = AsyncMock()
                async_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
                async_context_manager.__aexit__ = AsyncMock(return_value=None)

                with patch("app.utils.async_ocr.get_http_session") as mock_get_session:
                    mock_session = AsyncMock()
                    mock_session.post.return_value = async_context_manager
                    mock_get_session.return_value = mock_session

                    result = await async_ocr(sample_image_bytes, timeout=120)
                    assert result == expected_parsed_data

                    # Проверяем что таймаут передался
                    call_args = mock_session.post.call_args
                    timeout_arg = call_args.kwargs.get("timeout")
                    assert timeout_arg.total == 120


if __name__ == "__main__":
    pytest.main([__file__])
