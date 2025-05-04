import asyncio
import unittest
import time
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
import logging

from app.utils.api_decorators import (
    with_retry_backoff, 
    with_async_retry_backoff, 
    with_progress_stages,
    ErrorType,
    classify_error
)


class TestErrorClassification(unittest.TestCase):
    """Тесты для функции классификации ошибок"""
    
    def test_timeout_error(self):
        error = TimeoutError("Connection timed out")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.TIMEOUT)
        self.assertIn("вовремя", message)
        
    def test_rate_limit_error(self):
        error = Exception("Rate limit exceeded")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.RATE_LIMIT)
        self.assertIn("перегружен", message)
        
    def test_authentication_error(self):
        error = Exception("Authentication failed: Invalid API key")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.AUTHENTICATION)
        self.assertIn("авторизации", message)
        
    def test_validation_error(self):
        error = ValueError("Invalid format: expected JSON")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.VALIDATION)
        self.assertIn("формат", message)
        
    def test_server_error(self):
        error = Exception("Server error 500")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.SERVER)
        self.assertIn("сервера", message)
        
    def test_unknown_error(self):
        error = Exception("Some unexpected error")
        error_type, message = classify_error(error)
        self.assertEqual(error_type, ErrorType.UNKNOWN)
        self.assertIn("Неизвестная ошибка", message)


class TestRetryDecorator(unittest.TestCase):
    """Тесты для синхронного декоратора повторных попыток"""
    
    def setUp(self):
        self.mock_logger = MagicMock()
        logging.getLogger = MagicMock(return_value=self.mock_logger)
    
    def test_success_without_retry(self):
        @with_retry_backoff(max_retries=3)
        def test_func():
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
        # Проверяем, что не было попыток повтора (нет логов warning)
        self.mock_logger.warning.assert_not_called()
    
    def test_retry_until_success(self):
        mock_func = MagicMock()
        # Первые два вызова вызывают исключение, третий успешен
        mock_func.side_effect = [
            Exception("Temporary error"),
            Exception("Temporary error"),
            "success"
        ]
        
        @with_retry_backoff(max_retries=3, initial_backoff=0.01)
        def test_func():
            return mock_func()
        
        result = test_func()
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        # Проверяем, что были логи о повторных попытках
        self.assertEqual(self.mock_logger.warning.call_count, 2)
    
    def test_max_retries_exceeded(self):
        @with_retry_backoff(max_retries=2, initial_backoff=0.01)
        def test_func():
            raise Exception("Persistent error")
        
        with self.assertRaises(RuntimeError):
            test_func()
            
        # Проверяем, что были логи о повторных попытках
        self.assertEqual(self.mock_logger.warning.call_count, 2)
        # И финальный лог ошибки
        self.mock_logger.error.assert_called()
    
    def test_validation_error_no_retry(self):
        mock_func = MagicMock()
        # Функция всегда вызывает ошибку валидации
        mock_func.side_effect = ValueError("Validation error")
        
        @with_retry_backoff(max_retries=3, initial_backoff=0.01)
        def test_func():
            return mock_func()
        
        with self.assertRaises(RuntimeError):
            test_func()
            
        # Проверяем, что была только одна попытка (без повторов)
        self.assertEqual(mock_func.call_count, 1)
        # Не должно быть логов warning о повторных попытках
        self.mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
class TestAsyncRetryDecorator:
    """Тесты для асинхронного декоратора повторных попыток"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_logger = MagicMock()
        with patch('logging.getLogger', return_value=self.mock_logger):
            yield
    
    async def test_success_without_retry(self):
        @with_async_retry_backoff(max_retries=3)
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
        # Проверяем, что не было попыток повтора (нет логов warning)
        self.mock_logger.warning.assert_not_called()
    
    async def test_retry_until_success(self):
        mock_func = AsyncMock()
        # Первые два вызова вызывают исключение, третий успешен
        mock_func.side_effect = [
            Exception("Temporary error"),
            Exception("Temporary error"),
            "success"
        ]
        
        @with_async_retry_backoff(max_retries=3, initial_backoff=0.01)
        async def test_func():
            return await mock_func()
        
        result = await test_func()
        assert result == "success"
        assert mock_func.call_count == 3
        # Проверяем, что были логи о повторных попытках
        assert self.mock_logger.warning.call_count == 2
    
    async def test_max_retries_exceeded(self):
        @with_async_retry_backoff(max_retries=2, initial_backoff=0.01)
        async def test_func():
            raise Exception("Persistent error")
        
        with pytest.raises(RuntimeError):
            await test_func()
            
        # Проверяем, что были логи о повторных попытках
        assert self.mock_logger.warning.call_count == 2
        # И финальный лог ошибки
        self.mock_logger.error.assert_called()


@pytest.mark.asyncio
class TestProgressStages:
    """Тесты для декоратора отслеживания прогресса по этапам"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_logger = MagicMock()
        with patch('logging.getLogger', return_value=self.mock_logger):
            yield
    
    async def test_successful_completion(self):
        stages = {
            "stage1": "Этап 1",
            "stage2": "Этап 2",
            "stage3": "Этап 3"
        }
        
        update_progress = AsyncMock()
        
        @with_progress_stages(stages=stages)
        async def test_process(**kwargs):
            # В kwargs должны быть _stages и _stages_names
            assert "_stages" in kwargs
            assert "_stages_names" in kwargs
            assert "_req_id" in kwargs
            
            # Эмулируем успешное выполнение всех этапов
            kwargs["_stages"]["stage1"] = True
            kwargs["_stages"]["stage2"] = True
            kwargs["_stages"]["stage3"] = True
            return "success"
        
        result = await test_process(_update_progress=update_progress)
        assert result == "success"
        # Логи успешного завершения
        self.mock_logger.info.assert_called()
    
    async def test_error_handling(self):
        stages = {
            "stage1": "Этап 1",
            "stage2": "Этап 2", 
            "stage3": "Этап 3"
        }
        
        update_progress = AsyncMock()
        
        @with_progress_stages(stages=stages)
        async def test_process(**kwargs):
            # Успешно выполняем первый этап
            kwargs["_stages"]["stage1"] = True
            
            # Ошибка на втором этапе
            raise RuntimeError("Error in stage 2")
        
        with pytest.raises(RuntimeError) as excinfo:
            await test_process(_update_progress=update_progress)
        
        # Проверяем, что сообщение об ошибке содержит информацию о стадии
        assert "Этап 2" in str(excinfo.value)
        # Логи ошибки
        self.mock_logger.error.assert_called()
        
        # Проверяем, что функция обновления прогресса вызывалась с сообщением об ошибке
        update_progress.assert_called()
        call_kwargs = update_progress.call_args.kwargs
        assert "error_message" in call_kwargs
        assert "Этап 2" in call_kwargs["error_message"]


if __name__ == '__main__':
    unittest.main()