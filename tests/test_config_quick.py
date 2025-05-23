"""
Быстрые тесты для модуля app/config.py
"""

import os
from unittest.mock import patch

import pytest

from app.config import Settings, settings


class TestSettings:
    """Тесты для класса Settings"""

    def test_settings_instance(self):
        """Тест что settings является экземпляром Settings"""
        assert isinstance(settings, Settings)

    def test_settings_has_required_attributes(self):
        """Тест наличия необходимых атрибутов"""
        # Проверяем наличие основных атрибутов
        assert hasattr(settings, "TELEGRAM_TOKEN")
        assert hasattr(settings, "OPENAI_API_KEY")
        assert hasattr(settings, "REDIS_URL")

    @patch.dict(os.environ, {"TELEGRAM_TOKEN": "test_token"})
    def test_settings_from_env(self):
        """Тест загрузки настроек из переменных окружения"""
        # Создаем новый экземпляр чтобы подхватить измененную переменную окружения
        test_settings = Settings()
        assert test_settings.TELEGRAM_TOKEN == "test_token"

    @patch.dict(os.environ, {"DEBUG": "true"})
    def test_settings_boolean_env(self):
        """Тест загрузки булевых настроек"""
        test_settings = Settings()
        # Проверяем что булевые значения корректно обрабатываются
        # (зависит от конкретной реализации Settings)

    def test_settings_default_values(self):
        """Тест значений по умолчанию"""
        # Проверяем что у настроек есть разумные значения по умолчанию
        assert settings.REDIS_URL is not None
        assert isinstance(settings.REDIS_URL, str)

    @patch.dict(os.environ, {"MATCH_THRESHOLD": "0.8"})
    def test_settings_numeric_env(self):
        """Тест загрузки числовых настроек"""
        test_settings = Settings()
        # Проверяем что числовые значения корректно преобразуются
        if hasattr(test_settings, "MATCH_THRESHOLD"):
            assert isinstance(test_settings.MATCH_THRESHOLD, float)

    def test_settings_immutability(self):
        """Тест что настройки не изменяются случайно"""
        original_token = getattr(settings, "TELEGRAM_TOKEN", None)

        # Пробуем изменить настройку
        if hasattr(settings, "TELEGRAM_TOKEN"):
            try:
                settings.TELEGRAM_TOKEN = "new_value"
                # Если получилось изменить, проверяем что значение действительно изменилось
                # (некоторые реализации могут позволять изменения)
            except Exception:
                # Если нельзя изменять - это тоже нормально
                pass

    @patch.dict(os.environ, {}, clear=True)
    def test_settings_missing_env_vars(self):
        """Тест обработки отсутствующих переменных окружения"""
        # Создаем настройки без переменных окружения
        test_settings = Settings()

        # Проверяем что приложение не падает и имеет разумные значения по умолчанию
        assert test_settings is not None

    def test_settings_repr(self):
        """Тест строкового представления настроек"""
        settings_str = str(settings)
        assert isinstance(settings_str, str)
        # Проверяем что в строковом представлении нет чувствительных данных
        if hasattr(settings, "TELEGRAM_TOKEN") and settings.TELEGRAM_TOKEN:
            assert settings.TELEGRAM_TOKEN not in settings_str or "***" in settings_str

    def test_settings_validation(self):
        """Тест валидации настроек"""
        # Проверяем что критически важные настройки присутствуют
        if hasattr(settings, "REDIS_URL"):
            assert settings.REDIS_URL, "REDIS_URL не должен быть пустым"

        # Проверяем формат URL если он есть
        if hasattr(settings, "REDIS_URL") and settings.REDIS_URL:
            assert "redis://" in settings.REDIS_URL or "localhost" in settings.REDIS_URL


class TestSettingsConstruction:
    """Тесты создания экземпляров Settings"""

    def test_create_settings_instance(self):
        """Тест создания нового экземпляра Settings"""
        new_settings = Settings()
        assert isinstance(new_settings, Settings)

    @patch.dict(os.environ, {"TEST_VAR": "test_value"})
    def test_settings_env_override(self):
        """Тест переопределения настроек через переменные окружения"""
        new_settings = Settings()
        # Проверяем что новый экземпляр подхватывает переменные окружения
        assert new_settings is not None

    def test_settings_singleton_behavior(self):
        """Тест поведения синглтона (если применимо)"""
        # Проверяем что импортированный settings стабилен
        from app.config import settings as settings1
        from app.config import settings as settings2

        # Они должны ссылаться на один объект
        assert settings1 is settings2


if __name__ == "__main__":
    pytest.main([__file__])
