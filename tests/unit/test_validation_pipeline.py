from unittest.mock import MagicMock

import pytest

from app.models import ParsedData, Position
from app.validators.arithmetic import ArithmeticValidator
from app.validators.pipeline import ValidationPipeline
from app.validators.sanity import SanityValidator


@pytest.fixture
def mock_validators():
    """
    Мокирует валидаторы для тестирования пайплайна.
    """
    arithmetic_validator = MagicMock(spec=ArithmeticValidator)
    arithmetic_validator.validate.return_value = {"status": "ok", "issues": []}

    sanity_validator = MagicMock(spec=SanityValidator)
    sanity_validator.validate.return_value = {"status": "ok", "issues": []}

    return {"arithmetic": arithmetic_validator, "sanity": sanity_validator}


@pytest.fixture
def sample_data():
    """
    Создает тестовые данные ParsedData для проверки валидаторов.
    """
    return {
        "supplier": "Test Supplier",
        "date": "2025-01-01",
        "positions": [
            {"name": "Product 1", "qty": 2, "unit": "kg", "price": 100, "total_price": 200},
            {"name": "Product 2", "qty": 1, "unit": "pcs", "price": 50, "total_price": 50},
        ],
        "total_price": 250,
    }


def test_validation_pipeline_init():
    """
    Тест инициализации пайплайна валидации.
    """
    pipeline = ValidationPipeline()

    # Проверяем, что валидаторы созданы
    assert pipeline.validators is not None
    assert len(pipeline.validators) > 0

    # Проверяем, что каждый валидатор имеет метод validate
    for validator in pipeline.validators:
        assert hasattr(validator, "validate")


def test_validation_pipeline_validate_successful(mock_validators, sample_data):
    """
    Тест успешной валидации данных через пайплайн.
    """
    # Создаем пайплайн с моками валидаторов
    pipeline = ValidationPipeline()
    pipeline.validators = [mock_validators["arithmetic"], mock_validators["sanity"]]

    # Запускаем валидацию
    result = pipeline.validate(sample_data)

    # Проверяем, что каждый валидатор был вызван
    mock_validators["arithmetic"].validate.assert_called_once_with(sample_data)
    mock_validators["sanity"].validate.assert_called_once_with(sample_data)

    # Проверяем, что результат соответствует ожиданиям
    assert result["status"] == "success"
    assert "issues" in result
    assert result["issues"] == []  # Пустой список, так как оба валидатора вернули пустые списки


def test_validation_pipeline_validate_with_issues(mock_validators, sample_data):
    """
    Тест валидации с обнаруженными проблемами.
    """
    # Настраиваем моки валидаторов с ошибками
    mock_validators["arithmetic"].validate.return_value = {
        "status": "warning",
        "issues": ["Arithmetic issue 1"],
    }
    mock_validators["sanity"].validate.return_value = {
        "status": "warning",
        "issues": ["Sanity issue 1", "Sanity issue 2"],
    }

    # Создаем пайплайн с моками валидаторов
    pipeline = ValidationPipeline()
    pipeline.validators = [mock_validators["arithmetic"], mock_validators["sanity"]]

    # Запускаем валидацию
    result = pipeline.validate(sample_data)

    # Проверяем, что каждый валидатор был вызван
    mock_validators["arithmetic"].validate.assert_called_once_with(sample_data)
    mock_validators["sanity"].validate.assert_called_once_with(sample_data)

    # Проверяем, что результат содержит все проблемы
    assert result["status"] == "warning"  # Статус warning, так как оба валидатора вернули warning
    assert "issues" in result
    assert len(result["issues"]) == 3  # Все проблемы из обоих валидаторов
    assert "Arithmetic issue 1" in result["issues"]
    assert "Sanity issue 1" in result["issues"]
    assert "Sanity issue 2" in result["issues"]


def test_validation_pipeline_validate_with_errors(mock_validators, sample_data):
    """
    Тест валидации с серьезными ошибками.
    """
    # Настраиваем моки валидаторов с ошибками разной серьезности
    mock_validators["arithmetic"].validate.return_value = {
        "status": "warning",
        "issues": ["Arithmetic warning"],
    }
    mock_validators["sanity"].validate.return_value = {
        "status": "error",
        "issues": ["Critical sanity error"],
    }

    # Создаем пайплайн с моками валидаторов
    pipeline = ValidationPipeline()
    pipeline.validators = [mock_validators["arithmetic"], mock_validators["sanity"]]

    # Запускаем валидацию
    result = pipeline.validate(sample_data)

    # Проверяем, что результат имеет наиболее серьезный статус
    assert result["status"] == "error"  # Статус error, так как один из валидаторов вернул error
    assert "issues" in result
    assert len(result["issues"]) == 2  # Все проблемы из обоих валидаторов
    assert "Arithmetic warning" in result["issues"]
    assert "Critical sanity error" in result["issues"]


def test_validation_pipeline_validate_exception_handling(mock_validators, sample_data):
    """
    Тест обработки исключений в пайплайне валидации.
    """
    # Настраиваем мок валидатора, выбрасывающий исключение
    mock_validators["arithmetic"].validate.side_effect = Exception("Validator error")

    # Создаем пайплайн с моками валидаторов
    pipeline = ValidationPipeline()
    pipeline.validators = [mock_validators["arithmetic"], mock_validators["sanity"]]

    # Запускаем валидацию
    result = pipeline.validate(sample_data)

    # Проверяем, что результат содержит информацию об ошибке
    assert result["status"] == "error"
    assert "issues" in result
    assert any("Exception: Validator error" in issue for issue in result["issues"])

    # Проверяем, что второй валидатор все равно был вызван
    mock_validators["sanity"].validate.assert_called_once_with(sample_data)


def test_validation_pipeline_validate_different_input_types(mock_validators):
    """
    Тест валидации различных типов входных данных.
    """
    # Создаем пайплайн с моками валидаторов
    pipeline = ValidationPipeline()
    pipeline.validators = [mock_validators["arithmetic"], mock_validators["sanity"]]

    # Тестируем с объектом ParsedData
    parsed_data = ParsedData(
        supplier="Test Supplier",
        date="2025-01-01",
        positions=[Position(name="Product", qty=1, unit="pcs", price=100, total_price=100)],
        total_price=100,
    )
    result = pipeline.validate(parsed_data)
    assert result["status"] == "ok"

    # Тестируем с пустыми данными
    empty_data = {}
    result = pipeline.validate(empty_data)
    assert result["status"] == "ok"  # Валидаторы замокированы, поэтому возвращают ok

    # Тестируем с None
    result = pipeline.validate(None)
    assert result["status"] == "error"  # None должен вызывать ошибку валидации


def test_validation_pipeline_validate_full_pipeline_integration():
    """
    Интеграционный тест полного пайплайна валидации с реальными валидаторами.
    """
    # Создаем данные с ошибками для тестирования валидаторов
    data_with_errors = {
        "supplier": "Test Supplier",
        "date": "2025-01-01",
        "positions": [
            {
                "name": "Product 1",
                "qty": 2,
                "unit": "kg",
                "price": 100,
                # Ошибка арифметики: цена * количество = 200, но total_price = 300
                "total_price": 300,
            },
            {
                # Ошибка санитарии: слишком длинное название
                "name": "X" * 200,
                "qty": 1,
                "unit": "pcs",
                "price": 50,
                "total_price": 50,
            },
        ],
        # Ошибка арифметики: сумма total_price позиций = 350, но указано 250
        "total_price": 250,
    }

    # Создаем пайплайн с реальными валидаторами
    pipeline = ValidationPipeline()

    # Запускаем валидацию
    result = pipeline.validate(data_with_errors)

    # Проверяем, что валидация обнаружила ошибки
    assert result["status"] in ["warning", "error"]
    assert "issues" in result
    assert len(result["issues"]) > 0
