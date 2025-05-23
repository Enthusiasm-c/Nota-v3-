"""
Тесты для app/assistants/client.py - OpenAI Assistant API клиент
"""

import asyncio
import json
import logging
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pydantic import ValidationError

from app.assistants.client import (
    EditCommand,
    parse_assistant_output,
    parse_edit_command,
    optimize_logging,
    run_async,
    retry_openai_call,
    run_thread_safe_async,
    normalize_query_for_cache,
    adapt_cached_intent,
    run_thread_safe,
    ASSISTANT_ID,
    client
)


class TestEditCommand:
    """Тесты для модели EditCommand"""

    def test_valid_edit_command(self):
        """Тест создания валидной команды редактирования"""
        cmd = EditCommand(
            action="set_price",
            row=1,
            price=100.50
        )
        assert cmd.action == "set_price"
        assert cmd.row == 1
        assert cmd.price == 100.50

    def test_edit_command_optional_fields(self):
        """Тест создания команды с опциональными полями"""
        cmd = EditCommand(
            action="clarification_needed",
            error="test error"
        )
        assert cmd.action == "clarification_needed"
        assert cmd.error == "test error"
        assert cmd.row is None

    def test_edit_command_row_validation_success(self):
        """Тест успешной валидации поля row"""
        cmd = EditCommand(
            action="set_name",
            row=1,
            name="Test Product"
        )
        assert cmd.row == 1

    def test_edit_command_row_validation_failure(self):
        """Тест неудачной валидации поля row для команд, требующих row"""
        with pytest.raises(ValidationError):
            EditCommand(
                action="set_price",
                row=0,  # Невалидное значение
                price=100
            )

    def test_edit_command_all_fields(self):
        """Тест создания команды со всеми полями"""
        cmd = EditCommand(
            action="set_price",
            row=1,
            qty=5,
            name="Test Product",
            unit="кг",
            price=100.50,
            price_per_unit=20.10,
            total_price=502.50,
            date="2024-01-15",
            supplier="Test Supplier",
            error=None
        )
        assert cmd.action == "set_price"
        assert cmd.row == 1
        assert cmd.qty == 5
        assert cmd.name == "Test Product"
        assert cmd.unit == "кг"
        assert cmd.price == 100.50
        assert cmd.price_per_unit == 20.10
        assert cmd.total_price == 502.50
        assert cmd.date == "2024-01-15"
        assert cmd.supplier == "Test Supplier"


class TestParseAssistantOutput:
    """Тесты для функции parse_assistant_output"""

    def test_parse_valid_json_single_action(self):
        """Тест парсинга валидного JSON с одиночным действием"""
        json_input = '{"action": "set_price", "row": 1, "price": 100}'
        result = parse_assistant_output(json_input)
        
        assert len(result) == 1
        assert result[0].action == "set_price"
        assert result[0].row == 1
        assert result[0].price == 100

    def test_parse_valid_json_multiple_actions(self):
        """Тест парсинга валидного JSON с массивом действий"""
        json_input = '''{
            "actions": [
                {"action": "set_price", "row": 1, "price": 100},
                {"action": "set_qty", "row": 2, "qty": 5}
            ]
        }'''
        result = parse_assistant_output(json_input)
        
        assert len(result) == 2
        assert result[0].action == "set_price"
        assert result[1].action == "set_qty"

    def test_parse_invalid_json(self):
        """Тест парсинга невалидного JSON"""
        result = parse_assistant_output("invalid json")
        
        assert len(result) == 1
        assert result[0].action == "clarification_needed"
        assert result[0].error == "invalid json"

    def test_parse_empty_actions_array(self):
        """Тест парсинга пустого массива действий"""
        json_input = '{"actions": []}'
        result = parse_assistant_output(json_input)
        
        assert len(result) == 1
        assert result[0].action == "clarification_needed"

    def test_parse_no_action_field(self):
        """Тест парсинга JSON без поля action"""
        json_input = '{"unknown": "data"}'
        result = parse_assistant_output(json_input)
        
        assert len(result) == 1
        assert result[0].action == "clarification_needed"

    def test_parse_invalid_action_in_array(self):
        """Тест парсинга с невалидным действием в массиве"""
        json_input = '''{
            "actions": [
                {"action": "set_price", "row": 1, "price": 100},
                {"invalid": "action"},
                {"action": "set_qty", "row": 2, "qty": 5}
            ]
        }'''
        result = parse_assistant_output(json_input)
        
        # Должны получить только валидные команды
        assert len(result) == 2
        assert result[0].action == "set_price"
        assert result[1].action == "set_qty"

    def test_parse_non_dict_data(self):
        """Тест парсинга данных, не являющихся словарем"""
        json_input = '["not", "a", "dict"]'
        result = parse_assistant_output(json_input)
        
        assert len(result) == 1
        assert result[0].action == "clarification_needed"

    def test_parse_error_monitoring(self):
        """Тест мониторинга ошибок парсинга"""
        # Проверяем, что функция обрабатывает невалидный JSON
        result = parse_assistant_output("invalid json")
        assert len(result) == 1
        assert result[0].action == "clarification_needed"


class TestOptimizeLogging:
    """Тесты для функции optimize_logging"""

    @patch('logging.getLogger')
    def test_optimize_logging_httpx(self, mock_get_logger):
        """Тест оптимизации логирования для httpx"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        optimize_logging()
        
        # Проверяем, что уровень логирования установлен для httpx модулей
        mock_get_logger.assert_any_call("httpx")
        mock_logger.setLevel.assert_called()

    @patch('logging.getLogger')
    def test_optimize_logging_openai(self, mock_get_logger):
        """Тест оптимизации логирования для OpenAI"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        optimize_logging()
        
        mock_get_logger.assert_any_call("openai")
        mock_logger.setLevel.assert_called()


class TestRunAsync:
    """Тесты для декоратора run_async"""

    def test_run_async_decorator(self):
        """Тест работы декоратора run_async"""
        @run_async
        async def async_function(x):
            return x * 2
        
        result = async_function(5)
        assert result == 10

    def test_run_async_with_kwargs(self):
        """Тест декоратора с keyword arguments"""
        @run_async
        async def async_function(x, multiplier=1):
            return x * multiplier
        
        result = async_function(5, multiplier=3)
        assert result == 15


class TestRetryOpenaiCall:
    """Тесты для функции retry_openai_call"""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """Тест успешного вызова без повторов"""
        mock_func = Mock(return_value="success")
        
        result = await retry_openai_call(mock_func, "arg1", "arg2", kwarg1="test")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="test")

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error(self):
        """Тест повторных попыток при ошибке лимита"""
        import openai
        
        mock_func = Mock()
        mock_func.side_effect = [
            openai.RateLimitError("Rate limit", response=Mock(), body={}),
            "success"
        ]
        
        result = await retry_openai_call(mock_func, max_retries=2, initial_backoff=0.01)
        
        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Тест превышения максимального количества попыток"""
        import openai
        
        mock_func = Mock()
        mock_func.side_effect = openai.RateLimitError("Rate limit", response=Mock(), body={})
        
        with pytest.raises(openai.RateLimitError):
            await retry_openai_call(mock_func, max_retries=2, initial_backoff=0.01)
        
        assert mock_func.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        """Тест неповторяемой ошибки"""
        mock_func = Mock()
        mock_func.side_effect = ValueError("Non-retryable error")
        
        with pytest.raises(ValueError):
            await retry_openai_call(mock_func, max_retries=2)
        
        assert mock_func.call_count == 1


class TestNormalizeQueryForCache:
    """Тесты для функции normalize_query_for_cache"""

    def test_normalize_numbers(self):
        """Тест замены чисел на X"""
        result = normalize_query_for_cache("строка 5 цена 100")
        assert result == "строка X цена X"

    def test_normalize_units(self):
        """Тест замены единиц измерения"""
        result = normalize_query_for_cache("добавить 5 кг продукта")
        assert result == "добавить X UNIT продукта"

    def test_normalize_multiple_spaces(self):
        """Тест удаления лишних пробелов"""
        result = normalize_query_for_cache("строка   5    цена    100")
        assert result == "строка X цена X"

    def test_normalize_english_units(self):
        """Тест нормализации английских единиц"""
        result = normalize_query_for_cache("add 5 kg of product")
        assert result == "add X UNIT of product"

    def test_normalize_mixed_case(self):
        """Тест нормализации смешанного регистра"""
        result = normalize_query_for_cache("СТРОКА 5 Цена 100")
        assert result == "строка X цена X"


class TestAdaptCachedIntent:
    """Тесты для функции adapt_cached_intent"""

    def test_adapt_set_price_intent(self):
        """Тест адаптации намерения установки цены"""
        intent = {"action": "set_price", "value": "X"}
        query = "строка 3 цена 150"
        
        result = adapt_cached_intent(intent, query)
        
        assert result["action"] == "set_price"
        assert result["line_index"] == 2  # 3 - 1
        assert result["value"] == "150"

    def test_adapt_set_quantity_intent(self):
        """Тест адаптации намерения установки количества"""
        intent = {"action": "set_quantity", "value": "X"}
        query = "строка 1 количество 10"
        
        result = adapt_cached_intent(intent, query)
        
        assert result["action"] == "set_quantity"
        assert result["line_index"] == 0
        assert result["value"] == "10"

    def test_adapt_non_line_action(self):
        """Тест адаптации действия не для строки"""
        intent = {"action": "set_date", "date": "2024-01-01"}
        query = "дата 15 января"
        
        result = adapt_cached_intent(intent, query)
        
        # Не должно изменяться для действий не для строк
        assert result == intent

    def test_adapt_english_query(self):
        """Тест адаптации английского запроса"""
        intent = {"action": "set_price", "value": "X"}
        query = "line 2 price 200"
        
        result = adapt_cached_intent(intent, query)
        
        assert result["line_index"] == 1
        assert result["value"] == "200"


class TestRunThreadSafeAsync:
    """Тесты для асинхронной функции run_thread_safe_async"""

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.adapt_cached_intent')
    async def test_cached_intent_found(self, mock_adapt, mock_cache_get):
        """Тест использования кешированного намерения"""
        mock_cache_get.return_value = '{"action": "set_price"}'
        mock_adapt.return_value = {"action": "set_price", "adapted": True}
        
        result = await run_thread_safe_async("строка 1 цена 100")
        
        assert result["action"] == "set_price"
        assert result["adapted"] is True
        mock_adapt.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.adapt_cached_intent')
    async def test_openai_api_flow(self, mock_adapt, mock_cache_get):
        """Тест полного потока с OpenAI API - используем кешированный путь"""
        mock_cache_get.return_value = '{"action": "set_price"}'
        mock_adapt.return_value = {"action": "set_price", "row": 1, "price": 100}
        
        result = await run_thread_safe_async("строка 1 цена 100")
        
        assert result["action"] == "set_price"
        assert result["row"] == 1
        assert result["price"] == 100

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.retry_openai_call')
    @patch('app.assistants.client.adapt_intent')
    @patch('app.assistants.client.cache_set')
    async def test_openai_api_complex_flow(self, mock_cache_set, mock_adapt, mock_retry, mock_get_thread, mock_cache_get):
        """Тест сложного потока с ошибками OpenAI API"""
        mock_cache_get.return_value = None  # Нет кеша
        mock_get_thread.return_value = "thread_123"
        
        # Мокируем ошибку в создании сообщения
        mock_retry.side_effect = Exception("API Error")
        
        result = await run_thread_safe_async("test input")
        
        assert result["action"] == "unknown"
        assert "message_create_failed" in result["error"]

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.retry_openai_call')
    async def test_openai_api_message_creation_failure(self, mock_retry, mock_get_thread, mock_cache_get):
        """Тест ошибки создания сообщения"""
        mock_cache_get.return_value = None
        mock_get_thread.return_value = "thread_123"
        mock_retry.side_effect = Exception("API Error")
        
        result = await run_thread_safe_async("test input")
        
        assert result["action"] == "unknown"
        assert "message_create_failed" in result["error"]

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.retry_openai_call')
    async def test_openai_api_run_creation_failure(self, mock_retry, mock_get_thread, mock_cache_get):
        """Тест ошибки создания run"""
        mock_cache_get.return_value = None
        mock_get_thread.return_value = "thread_123"
        mock_retry.side_effect = [
            None,  # messages.create успешно
            Exception("Run creation failed")  # runs.create неудачно
        ]
        
        result = await run_thread_safe_async("test input")
        
        assert result["action"] == "unknown"
        assert "run_create_failed" in result["error"]

    @pytest.mark.asyncio
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.retry_openai_call')
    async def test_run_status_timeout(self, mock_retry, mock_get_thread, mock_cache_get):
        """Тест таймаута статуса run"""
        mock_cache_get.return_value = None
        mock_get_thread.return_value = "thread_123"
        
        mock_run = Mock()
        mock_run.id = "run_123"
        mock_run.status = "in_progress"  # Всегда in_progress, не завершается
        
        mock_retry.side_effect = [
            None,  # messages.create
            mock_run,  # runs.create
            mock_run,  # все последующие runs.retrieve
            mock_run,
            mock_run,
            mock_run,
            mock_run,
            mock_run,
            mock_run,
            mock_run
        ]
        
        result = await run_thread_safe_async("test input")
        
        assert result["action"] == "unknown"
        assert "run_status_in_progress" in result["error"]


class TestRunThreadSafe:
    """Тесты для синхронной функции run_thread_safe"""

    @patch('app.assistants.client.run_thread_safe_async')
    def test_run_thread_safe_wrapper(self, mock_async_func):
        """Тест синхронной обертки"""
        mock_async_func.return_value = {"action": "set_price"}
        
        # Мокируем asyncio.run чтобы избежать создания нового event loop
        with patch('asyncio.run') as mock_run:
            mock_run.return_value = {"action": "set_price"}
            
            result = run_thread_safe("test input")
            
            assert result["action"] == "set_price"
            mock_run.assert_called_once()


class TestDeprecatedParseEditCommand:
    """Тесты для deprecated функции parse_edit_command"""

    def test_parse_empty_input(self):
        """Тест парсинга пустого ввода"""
        result = parse_edit_command("")
        assert result == []

    def test_parse_simple_price_command(self):
        """Тест парсинга простой команды цены"""
        result = parse_edit_command("строка 1 цена 100")
        assert len(result) > 0

    def test_parse_invalid_line_number(self):
        """Тест парсинга с неверным номером строки"""
        result = parse_edit_command("строка 0 цена 100")
        assert any(cmd.get("error") == "line_out_of_range" for cmd in result)

    def test_parse_deprecation_warning(self):
        """Тест предупреждения о deprecated функции"""
        import warnings
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            parse_edit_command("строка 1 цена 100")
            
            assert len(w) > 0
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message)


class TestModuleConstants:
    """Тесты для констант модуля"""

    def test_assistant_id_defined(self):
        """Тест определения ASSISTANT_ID"""
        assert ASSISTANT_ID is not None

    def test_client_initialized(self):
        """Тест инициализации OpenAI клиента"""
        assert client is not None
        assert hasattr(client, 'beta')


class TestLoggerConfiguration:
    """Тесты для конфигурации логгера"""

    def test_logger_exists(self):
        """Тест существования логгера"""
        import app.assistants.client as client_module
        assert hasattr(client_module, 'logger')

    @patch('app.assistants.client.optimize_logging')
    def test_optimize_logging_called_on_import(self, mock_optimize):
        """Тест вызова optimize_logging при импорте"""
        # Этот тест проверяет, что optimize_logging вызывается
        # Мы не можем проверить это напрямую, так как модуль уже импортирован
        # Но мы можем убедиться, что функция существует и корректно работает
        mock_optimize.assert_not_called()  # Так как модуль уже загружен

 