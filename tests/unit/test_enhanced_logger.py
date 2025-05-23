import pytest
import logging
import time
from unittest.mock import MagicMock, patch
import json

from app.utils.enhanced_logger import (
    log_indonesian_invoice,
    log_format_issues,
    PerformanceTimer,
    setup_enhanced_logging
)


@pytest.fixture
def mock_logger():
    """
    Фикстура, возвращающая мок логгера.
    """
    return MagicMock(spec=logging.Logger)


def test_log_indonesian_invoice(mock_logger):
    """
    Тест функции логирования индонезийских накладных.
    """
    req_id = "test-123"
    data = {
        "supplier": "Indonesian Supplier",
        "positions": [
            {"name": "Nasi Goreng", "qty": 2, "unit": "pcs", "price": 50000}
        ],
        "total_price": 100000
    }
    phase = "test-phase"
    
    with patch('app.utils.enhanced_logger.logging.getLogger', return_value=mock_logger):
        # Вызываем функцию
        log_indonesian_invoice(req_id, data, phase)
        
        # Проверяем, что логирование произошло только один раз
        mock_logger.info.assert_called_once()
        
        # Проверяем, что в логе содержится нужная информация
        log_message = mock_logger.info.call_args[0][0]
        assert req_id in log_message
        assert phase in log_message
        assert "Indonesian" in log_message
        
        # Проверяем, что данные были сериализованы в JSON
        log_data = mock_logger.info.call_args[0][1]
        assert isinstance(log_data, str)
        
        # Проверяем, что можно распарсить JSON
        parsed_data = json.loads(log_data)
        assert parsed_data["supplier"] == "Indonesian Supplier"
        assert len(parsed_data["positions"]) == 1
        assert parsed_data["positions"][0]["name"] == "Nasi Goreng"


def test_log_indonesian_invoice_non_indonesian(mock_logger):
    """
    Тест функции логирования для не-индонезийских накладных.
    """
    req_id = "test-123"
    data = {
        "supplier": "Regular Supplier",
        "positions": [
            {"name": "Pizza", "qty": 1, "unit": "pcs", "price": 10}
        ],
        "total_price": 10
    }
    phase = "test-phase"
    
    with patch('app.utils.enhanced_logger.logging.getLogger', return_value=mock_logger):
        # Вызываем функцию
        log_indonesian_invoice(req_id, data, phase)
        
        # Проверяем, что логирование не произошло (не индонезийская накладная)
        mock_logger.info.assert_not_called()


def test_log_indonesian_invoice_error_handling(mock_logger):
    """
    Тест обработки ошибок в функции логирования индонезийских накладных.
    """
    req_id = "test-123"
    # Данные, которые вызовут ошибку сериализации
    data = {
        "supplier": "Indonesian Supplier",
        "positions": [
            {"name": "Nasi Goreng", "qty": 2, "unit": "pcs", "price": 50000, 
             "circular_ref": None}  # Создаем циклическую ссылку
        ],
        "total_price": 100000
    }
    # Создаем циклическую ссылку
    data["positions"][0]["circular_ref"] = data
    
    phase = "test-phase"
    
    with patch('app.utils.enhanced_logger.logging.getLogger', return_value=mock_logger):
        # Вызываем функцию
        log_indonesian_invoice(req_id, data, phase)
        
        # Проверяем, что произошло логирование ошибки
        mock_logger.error.assert_called_once()
        
        # Проверяем, что в логе содержится информация об ошибке
        log_message = mock_logger.error.call_args[0][0]
        assert req_id in log_message
        assert "Error logging Indonesian" in log_message


def test_log_format_issues(mock_logger):
    """
    Тест функции логирования проблем с форматом.
    """
    req_id = "test-123"
    field = "test-field"
    value = "test-value"
    expected = "expected-value"
    
    with patch('app.utils.enhanced_logger.logging.getLogger', return_value=mock_logger):
        # Вызываем функцию
        log_format_issues(req_id, field, value, expected)
        
        # Проверяем, что произошло логирование
        mock_logger.warning.assert_called_once()
        
        # Проверяем, что в логе содержится нужная информация
        log_message = mock_logger.warning.call_args[0][0]
        assert req_id in log_message
        assert field in log_message
        assert str(value) in log_message
        assert expected in log_message


def test_performance_timer_basic():
    """
    Базовый тест таймера производительности.
    """
    req_id = "test-123"
    operation = "test-operation"
    
    with patch('app.utils.enhanced_logger.logging.getLogger') as mock_get_logger:
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger
        
        # Используем таймер в контексте менеджера
        with PerformanceTimer(req_id, operation):
            # Имитируем некоторую работу
            time.sleep(0.1)
        
        # Проверяем, что произошло логирование
        mock_logger.info.assert_called_once()
        
        # Проверяем, что в логе содержится нужная информация
        log_message = mock_logger.info.call_args[0][0]
        assert req_id in log_message
        assert operation in log_message
        assert "completed in" in log_message
        
        # Проверяем, что время выполнения положительное
        execution_time = float(log_message.split()[-2])
        assert execution_time > 0


def test_performance_timer_error_handling():
    """
    Тест обработки ошибок в таймере производительности.
    """
    req_id = "test-123"
    operation = "test-operation"
    
    with patch('app.utils.enhanced_logger.logging.getLogger') as mock_get_logger:
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger
        
        # Используем таймер в контексте менеджера с ошибкой
        try:
            with PerformanceTimer(req_id, operation):
                # Вызываем ошибку
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Проверяем, что произошло логирование ошибки
        mock_logger.error.assert_called_once()
        
        # Проверяем, что в логе содержится информация об ошибке
        log_message = mock_logger.error.call_args[0][0]
        assert req_id in log_message
        assert operation in log_message
        assert "failed after" in log_message
        assert "ValueError" in mock_logger.error.call_args[0][1]
        
        # Проверяем, что время выполнения положительное
        execution_time = float(log_message.split()[-2])
        assert execution_time > 0


def test_setup_enhanced_logging():
    """
    Тест настройки расширенного логирования.
    """
    with patch('app.utils.enhanced_logger.logging.getLogger') as mock_get_logger, \
         patch('app.utils.enhanced_logger.logging.StreamHandler') as mock_stream_handler, \
         patch('app.utils.enhanced_logger.logging.Formatter') as mock_formatter:
        
        mock_logger = MagicMock(spec=logging.Logger)
        mock_get_logger.return_value = mock_logger
        
        # Вызываем функцию настройки логирования
        logger = setup_enhanced_logging("test-logger")
        
        # Проверяем, что был создан логгер
        mock_get_logger.assert_called_once_with("test-logger")
        
        # Проверяем, что был создан обработчик и форматтер
        mock_stream_handler.assert_called_once()
        mock_formatter.assert_called_once()
        
        # Проверяем, что обработчик был добавлен к логгеру
        mock_logger.addHandler.assert_called_once()
        
        # Проверяем, что был установлен уровень логирования
        mock_logger.setLevel.assert_called_once()
        
        # Проверяем, что функция вернула логгер
        assert logger == mock_logger