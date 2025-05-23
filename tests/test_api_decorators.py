"""
Тесты для app/utils/api_decorators.py - декораторы для API запросов
"""

import asyncio
import pytest
import time
import uuid
from unittest.mock import Mock, patch, AsyncMock
import logging

from app.utils.api_decorators import (
    FriendlyException,
    ErrorType,
    classify_error,
    with_retry_backoff,
    with_async_retry_backoff,
    with_progress_stages,
    update_stage,
    update_stage_async
)


class TestFriendlyException:
    """Тесты для класса FriendlyException"""

    def test_friendly_exception_init(self):
        """Тест инициализации FriendlyException"""
        message = "Тестовое сообщение"
        exc = FriendlyException(message)
        assert str(exc) == message
        assert exc.friendly_message == message

    def test_friendly_exception_inheritance(self):
        """Тест наследования от Exception"""
        exc = FriendlyException("test")
        assert isinstance(exc, Exception)


class TestErrorType:
    """Тесты для класса ErrorType"""

    def test_error_type_constants(self):
        """Тест констант ErrorType"""
        assert ErrorType.TIMEOUT == "timeout"
        assert ErrorType.RATE_LIMIT == "rate_limit"
        assert ErrorType.VALIDATION == "validation"
        assert ErrorType.AUTHENTICATION == "authentication"
        assert ErrorType.SERVER == "server"
        assert ErrorType.CLIENT == "client"
        assert ErrorType.NETWORK == "network"
        assert ErrorType.UNKNOWN == "unknown"


class TestClassifyError:
    """Тесты для функции classify_error"""

    def test_classify_timeout_error(self):
        """Тест классификации ошибок таймаута"""
        error = Exception("Connection timeout")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.TIMEOUT
        assert "не ответил вовремя" in message

        error = Exception("Request timed out")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.TIMEOUT

    def test_classify_rate_limit_error(self):
        """Тест классификации ошибок лимита запросов"""
        error = Exception("Rate limit exceeded")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.RATE_LIMIT
        assert "перегружен" in message

        error = Exception("Too many requests")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.RATE_LIMIT

        error = Exception("HTTP 429")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.RATE_LIMIT

    def test_classify_authentication_error(self):
        """Тест классификации ошибок авторизации"""
        error = Exception("Authentication failed")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.AUTHENTICATION
        assert "авторизации" in message

        error = Exception("Invalid API key")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.AUTHENTICATION

        error = Exception("HTTP 401 Unauthorized")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.AUTHENTICATION

    def test_classify_validation_error(self):
        """Тест классификации ошибок валидации"""
        error = Exception("Validation failed")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.VALIDATION
        assert "формат данных" in message

        error = Exception("Invalid format")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.VALIDATION

        error = Exception("HTTP 400 Bad Request")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.VALIDATION

    def test_classify_server_error(self):
        """Тест классификации серверных ошибок"""
        error = Exception("Internal server error")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.SERVER
        assert "стороне сервера" in message

        error = Exception("HTTP 500")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.SERVER

        error = Exception("HTTP 502 Bad Gateway")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.SERVER

    def test_classify_client_error(self):
        """Тест классификации клиентских ошибок"""
        error = Exception("Client error occurred")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.CLIENT
        assert "Некорректный запрос" in message

        error = Exception("Bad request format")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.CLIENT

    def test_classify_network_error(self):
        """Тест классификации сетевых ошибок"""
        error = Exception("Network connection failed")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.NETWORK
        assert "сетевым подключением" in message

        error = Exception("Host unreachable")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.NETWORK

        error = Exception("Connection refused")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.NETWORK

    def test_classify_unknown_error(self):
        """Тест классификации неизвестных ошибок"""
        error = Exception("Some random error")
        error_type, message = classify_error(error)
        assert error_type == ErrorType.UNKNOWN
        assert "Неизвестная ошибка" in message


class TestWithRetryBackoff:
    """Тесты для декоратора with_retry_backoff"""

    def test_successful_call_no_retry(self):
        """Тест успешного вызова без повторов"""
        @with_retry_backoff(max_retries=3)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_retry_on_exception(self):
        """Тест повтора при исключении"""
        call_count = 0

        @with_retry_backoff(max_retries=2, initial_backoff=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 3

    def test_max_retries_exceeded(self):
        """Тест превышения максимального количества повторов"""
        @with_retry_backoff(max_retries=2, initial_backoff=0.01)
        def test_func():
            raise Exception("Persistent error")

        with pytest.raises(RuntimeError) as exc_info:
            test_func()

        assert "API error" in str(exc_info.value)

    def test_validation_error_no_retry(self):
        """Тест что ошибки валидации не повторяются"""
        call_count = 0

        @with_retry_backoff(max_retries=3, initial_backoff=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Validation error")

        with pytest.raises(ValueError):
            test_func()
        
        assert call_count == 1

    def test_specific_error_types_retry(self):
        """Тест повтора только для определенных типов ошибок"""
        call_count = 0

        @with_retry_backoff(max_retries=2, initial_backoff=0.01, error_types=[ErrorType.TIMEOUT])
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout error")  # Будет повторено
            elif call_count == 2:
                raise Exception("server error")   # Не будет повторено
            return "success"

        with pytest.raises(Exception) as exc_info:
            test_func()

        assert "server error" in str(exc_info.value)
        assert call_count == 2

    def test_backoff_calculation(self):
        """Тест расчета задержки"""
        call_times = []

        @with_retry_backoff(max_retries=2, initial_backoff=0.1, backoff_factor=2.0)
        def test_func():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise Exception("Retry error")
            return "success"

        result = test_func()
        assert result == "success"
        assert len(call_times) == 3
        
        # Проверяем что задержки увеличиваются
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay1 >= 0.1
        assert delay2 >= 0.2

    @patch('app.utils.api_decorators.uuid.uuid4')
    def test_request_id_generation(self, mock_uuid):
        """Тест генерации ID запроса"""
        mock_uuid.return_value.hex = "abcdef123456"

        @with_retry_backoff(max_retries=1)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"
        mock_uuid.assert_called_once()

    def test_custom_request_id(self):
        """Тест использования пользовательского ID запроса"""
        @with_retry_backoff(max_retries=1)
        def test_func():
            return "success"

        result = test_func(_req_id="custom123")
        assert result == "success"

    @patch('app.utils.api_decorators.logging.getLogger')
    def test_logging_on_retry(self, mock_get_logger):
        """Тест логирования при повторах"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        call_count = 0

        @with_retry_backoff(max_retries=1, initial_backoff=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Retry error")
            return "success"

        result = test_func()
        assert result == "success"
        
        # Проверяем что было логирование
        mock_logger.info.assert_called()
        mock_logger.warning.assert_called()


class TestWithAsyncRetryBackoff:
    """Тесты для декоратора with_async_retry_backoff"""

    @pytest.mark.asyncio
    async def test_successful_async_call_no_retry(self):
        """Тест успешного асинхронного вызова без повторов"""
        @with_async_retry_backoff(max_retries=3)
        async def test_func():
            return "async_success"

        result = await test_func()
        assert result == "async_success"

    @pytest.mark.asyncio
    async def test_async_retry_on_exception(self):
        """Тест повтора при исключении в асинхронной функции"""
        call_count = 0

        @with_async_retry_backoff(max_retries=2, initial_backoff=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary async error")
            return "async_success"

        result = await test_func()
        assert result == "async_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_retries_exceeded(self):
        """Тест превышения максимального количества повторов в асинхронной функции"""
        @with_async_retry_backoff(max_retries=2, initial_backoff=0.01)
        async def test_func():
            raise Exception("Persistent async error")

        with pytest.raises(RuntimeError) as exc_info:
            await test_func()
        
        assert "Persistent async error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_validation_error_no_retry(self):
        """Тест что ошибки валидации не повторяются в асинхронной функции"""
        call_count = 0

        @with_async_retry_backoff(max_retries=3, initial_backoff=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise Exception("validation failed")

        with pytest.raises(RuntimeError):
            await test_func()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_authentication_error_no_retry(self):
        """Тест что ошибки авторизации не повторяются в асинхронной функции"""
        call_count = 0

        @with_async_retry_backoff(max_retries=3, initial_backoff=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise Exception("authentication failed")

        with pytest.raises(RuntimeError):
            await test_func()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_specific_error_types_retry(self):
        """Тест повтора только для определенных типов ошибок в асинхронной функции"""
        call_count = 0

        @with_async_retry_backoff(max_retries=2, initial_backoff=0.01, error_types=[ErrorType.TIMEOUT])
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout error")  # Будет повторено
            elif call_count == 2:
                raise Exception("server error")   # Не будет повторено
            return "success"

        with pytest.raises(RuntimeError):
            await test_func()
        
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_backoff_calculation(self):
        """Тест расчета задержки в асинхронной функции"""
        call_times = []

        @with_async_retry_backoff(max_retries=2, initial_backoff=0.1, backoff_factor=2.0)
        async def test_func():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise Exception("Retry error")
            return "success"

        result = await test_func()
        assert result == "success"
        assert len(call_times) == 3
        
        # Проверяем что задержки увеличиваются
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay1 >= 0.1
        assert delay2 >= 0.2

    @pytest.mark.asyncio
    async def test_async_friendly_exception_preservation(self):
        """Тест сохранения friendly_message в исключениях"""
        @with_async_retry_backoff(max_retries=1, initial_backoff=0.01)
        async def test_func():
            exc = Exception("Test error")
            exc.friendly_message = "Friendly test message"
            raise exc

        with pytest.raises(Exception) as exc_info:
            await test_func()
        
        assert exc_info.value.friendly_message == "Friendly test message"


class TestWithProgressStages:
    """Тесты для декоратора with_progress_stages"""

    @pytest.mark.asyncio
    async def test_progress_stages_successful(self):
        """Тест успешного выполнения с отслеживанием этапов"""
        stages = {
            "stage1": "Первый этап",
            "stage2": "Второй этап"
        }

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            assert "_stages" in kwargs
            assert "_stages_names" in kwargs
            assert "_req_id" in kwargs
            return "success"

        result = await test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_progress_stages_with_custom_req_id(self):
        """Тест с пользовательским ID запроса"""
        stages = {"stage1": "Тест"}

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            assert kwargs["_req_id"] == "custom123"
            return "success"

        result = await test_func(_req_id="custom123")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_progress_stages_with_update_progress(self):
        """Тест с функцией обновления прогресса"""
        stages = {"stage1": "Тест"}
        update_calls = []

        async def mock_update_progress(**kwargs):
            update_calls.append(kwargs)

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            return "success"

        result = await test_func(_update_progress=mock_update_progress)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_progress_stages_error_handling(self):
        """Тест обработки ошибок с этапами"""
        stages = {
            "stage1": "Первый этап",
            "stage2": "Второй этап"
        }

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            # Помечаем первый этап как выполненный
            kwargs["_stages"]["stage1"] = True
            # Ошибка на втором этапе
            raise Exception("Test error")

        with pytest.raises(FriendlyException) as exc_info:
            await test_func()
        
        assert "Второй этап" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_progress_stages_error_with_update_progress(self):
        """Тест обработки ошибок с обновлением UI"""
        stages = {"stage1": "Тест"}
        update_calls = []

        async def mock_update_progress(**kwargs):
            update_calls.append(kwargs)

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            raise Exception("Test error")

        with pytest.raises(FriendlyException):
            await test_func(_update_progress=mock_update_progress)
        
        # Проверяем что была попытка обновить UI с ошибкой
        assert len(update_calls) == 1
        assert "error_message" in update_calls[0]

    @pytest.mark.asyncio
    async def test_progress_stages_ui_update_error_ignored(self):
        """Тест что ошибки обновления UI игнорируются"""
        stages = {"stage1": "Тест"}

        async def failing_update_progress(**kwargs):
            raise Exception("UI update failed")

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            raise Exception("Main error")

        # Основная ошибка должна быть выброшена, ошибка UI - проигнорирована
        with pytest.raises(FriendlyException) as exc_info:
            await test_func(_update_progress=failing_update_progress)
        
        assert "Main error" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('app.utils.api_decorators.logging.getLogger')
    async def test_progress_stages_logging(self, mock_get_logger):
        """Тест логирования в декораторе этапов"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        stages = {"stage1": "Тест"}

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            return "success"

        result = await test_func()
        assert result == "success"
        
        # Проверяем что было логирование завершения
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_progress_stages_with_stage_updates(self):
        """Тест этапов с обновлениями внутри функции"""
        stages = {
            "download": "Загрузка",
            "process": "Обработка", 
            "upload": "Сохранение"
        }

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            # Симулируем выполнение этапов
            await update_stage_async("download", kwargs)
            await asyncio.sleep(0.01)
            
            await update_stage_async("process", kwargs)
            await asyncio.sleep(0.01)
            
            await update_stage_async("upload", kwargs)
            return "completed"

        result = await test_func()
        assert result == "completed"


class TestUpdateStage:
    """Тесты для функции update_stage"""

    def test_update_stage_success(self):
        """Тест успешного обновления этапа"""
        context = {
            "_stages": {"stage1": False, "stage2": False},
            "_stages_names": {"stage1": "Первый этап", "stage2": "Второй этап"}
        }

        result = update_stage("stage1", context)
        
        assert result["_stages"]["stage1"] is True
        assert result["_stages"]["stage2"] is False

    def test_update_stage_with_update_func(self):
        """Тест обновления этапа с функцией обновления"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }
        
        update_calls = []

        def mock_update_func(**kwargs):
            update_calls.append(kwargs)

        update_stage("stage1", context, mock_update_func)
        
        assert context["_stages"]["stage1"] is True
        assert len(update_calls) == 1
        assert update_calls[0]["stage"] == "stage1"
        assert update_calls[0]["stage_name"] == "Первый этап"

    def test_update_stage_with_async_update_func(self):
        """Тест обновления этапа с асинхронной функцией обновления"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }

        async def mock_async_update(**kwargs):
            pass

        # Не должно вызывать исключений
        update_stage("stage1", context, mock_async_update)
        assert context["_stages"]["stage1"] is True

    def test_update_stage_invalid_context(self):
        """Тест обновления этапа с невалидным контекстом"""
        context = {}
        
        result = update_stage("stage1", context)
        assert result == context

    def test_update_stage_invalid_stage(self):
        """Тест обновления несуществующего этапа"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }

        update_stage("invalid_stage", context)
        
        # Состояние не должно измениться
        assert context["_stages"]["stage1"] is False

    def test_update_stage_update_func_error_ignored(self):
        """Тест что ошибки функции обновления игнорируются"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }

        def failing_update_func(**kwargs):
            raise Exception("Update failed")

        # Не должно вызывать исключений
        update_stage("stage1", context, failing_update_func)
        assert context["_stages"]["stage1"] is True


class TestUpdateStageAsync:
    """Тесты для функции update_stage_async"""

    @pytest.mark.asyncio
    async def test_update_stage_async_success(self):
        """Тест успешного асинхронного обновления этапа"""
        context = {
            "_stages": {"stage1": False, "stage2": False},
            "_stages_names": {"stage1": "Первый этап", "stage2": "Второй этап"}
        }

        result = await update_stage_async("stage1", context)
        
        assert result["_stages"]["stage1"] is True
        assert result["_stages"]["stage2"] is False

    @pytest.mark.asyncio
    async def test_update_stage_async_with_sync_update_func(self):
        """Тест асинхронного обновления этапа с синхронной функцией обновления"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }
        
        update_calls = []

        def mock_update_func(**kwargs):
            update_calls.append(kwargs)

        await update_stage_async("stage1", context, mock_update_func)
        
        assert context["_stages"]["stage1"] is True
        assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_update_stage_async_with_async_update_func(self):
        """Тест асинхронного обновления этапа с асинхронной функцией обновления"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }
        
        update_calls = []

        async def mock_async_update(**kwargs):
            update_calls.append(kwargs)

        await update_stage_async("stage1", context, mock_async_update)
        
        assert context["_stages"]["stage1"] is True
        assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_update_stage_async_invalid_context(self):
        """Тест асинхронного обновления этапа с невалидным контекстом"""
        context = {}
        
        result = await update_stage_async("stage1", context)
        assert result == context

    @pytest.mark.asyncio
    async def test_update_stage_async_update_func_error_ignored(self):
        """Тест что ошибки асинхронной функции обновления игнорируются"""
        context = {
            "_stages": {"stage1": False},
            "_stages_names": {"stage1": "Первый этап"}
        }

        async def failing_async_update(**kwargs):
            raise Exception("Async update failed")

        # Не должно вызывать исключений
        await update_stage_async("stage1", context, failing_async_update)
        assert context["_stages"]["stage1"] is True


class TestIntegration:
    """Интеграционные тесты"""

    @pytest.mark.asyncio
    async def test_combined_decorators(self):
        """Тест комбинирования декораторов"""
        stages = {"process": "Обработка"}
        call_count = 0

        @with_async_retry_backoff(max_retries=2, initial_backoff=0.01)
        @with_progress_stages(stages)
        async def test_func(**kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                raise Exception("Temporary error")
            
            # Обновляем этап
            kwargs["_stages"]["process"] = True
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 2

    def test_sync_retry_with_different_error_types(self):
        """Тест синхронного повтора с разными типами ошибок"""
        errors = [
            Exception("timeout occurred"),
            Exception("rate limit exceeded"),
            Exception("server error 500")
        ]
        
        call_count = 0

        @with_retry_backoff(max_retries=3, initial_backoff=0.01)
        def test_func():
            nonlocal call_count
            if call_count < len(errors):
                error = errors[call_count]
                call_count += 1
                raise error
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == len(errors)

    @pytest.mark.asyncio
    async def test_progress_stages_with_stage_updates(self):
        """Тест этапов с обновлениями внутри функции"""
        stages = {
            "download": "Загрузка",
            "process": "Обработка", 
            "upload": "Сохранение"
        }

        @with_progress_stages(stages)
        async def test_func(**kwargs):
            # Симулируем выполнение этапов
            await update_stage_async("download", kwargs)
            await asyncio.sleep(0.01)
            
            await update_stage_async("process", kwargs)
            await asyncio.sleep(0.01)
            
            await update_stage_async("upload", kwargs)
            return "completed"

        result = await test_func()
        assert result == "completed"
