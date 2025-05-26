#!/usr/bin/env python3
"""
Тест готовности к деплою на сервер.
Проверяет все критически важные компоненты перед развертыванием.
"""

import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDeploymentReadiness:
    """Критически важные тесты для деплоя."""

    def test_import_core_modules(self):
        """Проверка импорта всех основных модулей."""
        try:
            from app import config, data_loader, matcher, alias
            from app.services.unified_syrve_client import UnifiedSyrveClient
            from app.syrve_mapping import get_syrve_guid
            assert True, "All core modules imported successfully"
        except ImportError as e:
            pytest.fail(f"Failed to import core modules: {e}")

    def test_data_loading(self):
        """Проверка загрузки данных."""
        from app.data_loader import load_products, load_suppliers
        
        products = load_products()
        suppliers = load_suppliers()
        
        assert len(products) > 500, f"Expected >500 products, got {len(products)}"
        assert len(suppliers) > 0, f"Expected >0 suppliers, got {len(suppliers)}"
        
        # Проверка структуры продуктов
        sample_product = products[0]
        required_fields = ['id', 'name']
        for field in required_fields:
            assert hasattr(sample_product, field) or field in sample_product, f"Product missing field: {field}"

    def test_improved_matcher_critical_cases(self):
        """Проверка работы улучшенного matcher для критических случаев."""
        from app.matcher import calculate_string_similarity, fuzzy_find
        from app.data_loader import load_products
        
        # Критические тесты для продакшена
        critical_tests = [
            ("mayonnaise", "mayo", 0.75),  # Основная проблема
            ("mozzarella", "mozzarela", 0.75),
            ("chicken breast", "chicken", 0.75),
            ("tomato sauce", "tomato", 0.75),
        ]
        
        products = load_products()
        
        for query, expected_match, min_score in critical_tests:
            score = calculate_string_similarity(query, expected_match)
            assert score >= min_score, f"Critical test failed: {query} -> {expected_match} = {score:.3f} < {min_score}"
            
            # Тест через fuzzy_find
            results = fuzzy_find(query, products, threshold=0.75, limit=1)
            assert len(results) > 0, f"No fuzzy_find results for: {query}"
            assert results[0]["score"] >= 0.75, f"Low score in fuzzy_find for {query}: {results[0]['score']:.3f}"

    def test_syrve_mapping_integrity(self):
        """Проверка целостности мапинга Syrve."""
        from app.syrve_mapping import get_syrve_guid
        from app.data_loader import load_products
        
        products = load_products()
        
        # Проверяем критические продукты
        critical_products = [
            "2bba7486-15c4-4808-9d29-a4a4ae606b1a",  # mayo
            "a815ce5a-5d2a-45e3-8187-318b6daa76ec",  # mozzarella
        ]
        
        for product_id in critical_products:
            guid = get_syrve_guid(product_id)
            assert guid is not None, f"No Syrve mapping for critical product: {product_id}"
            assert len(guid) > 20, f"Invalid GUID format for {product_id}: {guid}"

    def test_syrve_client_initialization(self):
        """Проверка инициализации Syrve клиента."""
        from app.services.unified_syrve_client import UnifiedSyrveClient
        from app.config import settings
        
        # Проверка что клиент может быть создан
        try:
            client = UnifiedSyrveClient(
                base_url=settings.SYRVE_SERVER_URL,
                login=settings.SYRVE_LOGIN,
                password=settings.SYRVE_PASSWORD,
                verify_ssl=settings.VERIFY_SSL
            )
            assert client is not None
            assert client.base_url == settings.SYRVE_SERVER_URL
        except Exception as e:
            pytest.fail(f"Failed to initialize Syrve client: {e}")

    def test_config_settings(self):
        """Проверка критических настроек конфигурации."""
        from app.config import settings
        
        # Критические настройки для продакшена
        critical_settings = [
            'TELEGRAM_BOT_TOKEN',
            'SYRVE_SERVER_URL',
            'SYRVE_LOGIN',
            'MATCH_THRESHOLD'
        ]
        
        for setting in critical_settings:
            value = getattr(settings, setting, None)
            assert value is not None, f"Critical setting missing: {setting}"
            assert str(value).strip() != "", f"Critical setting empty: {setting}"

    def test_file_permissions_and_existence(self):
        """Проверка существования и прав доступа к файлам."""
        from pathlib import Path
        
        critical_files = [
            'data/base_products.csv',
            'data/base_suppliers.csv', 
            'data/syrve_mapping.csv',
            'data/aliases.csv',
            'app/config.py',
            'app/matcher.py',
            'app/services/unified_syrve_client.py',
            'restart_bot.sh'
        ]
        
        project_root = Path(__file__).parent.parent
        
        for file_path in critical_files:
            full_path = project_root / file_path
            assert full_path.exists(), f"Critical file missing: {file_path}"
            assert full_path.is_file(), f"Path is not a file: {file_path}"
            
            # Проверка прав на чтение
            assert full_path.stat().st_mode & 0o444, f"File not readable: {file_path}"

    def test_bot_restart_script(self):
        """Проверка скрипта перезапуска бота."""
        from pathlib import Path
        
        script_path = Path(__file__).parent.parent / "restart_bot.sh"
        assert script_path.exists(), "Bot restart script missing"
        
        # Проверка прав на выполнение
        assert script_path.stat().st_mode & 0o111, "Bot restart script not executable"
        
        # Проверка содержимого скрипта
        content = script_path.read_text()
        assert "pkill" in content, "Script missing process kill logic"
        assert "bot.py" in content, "Script missing bot.py reference"

    def test_memory_and_performance_basics(self):
        """Базовые тесты производительности."""
        import time
        from app.matcher import calculate_string_similarity
        
        # Тест производительности matcher
        start_time = time.time()
        
        test_pairs = [
            ("mayonnaise", "mayo"),
            ("chicken breast", "chicken"),
            ("tomato sauce", "tomato")
        ] * 50  # 150 вычислений
        
        for s1, s2 in test_pairs:
            calculate_string_similarity(s1, s2)
            
        execution_time = time.time() - start_time
        
        # 150 вычислений должны выполняться менее чем за 1 секунду
        assert execution_time < 1.0, f"Performance test failed: {execution_time:.3f}s for 150 calculations"

    def test_critical_environment_variables(self):
        """Проверка критических переменных окружения."""
        from app.config import settings
        
        # Переменные которые должны быть установлены в продакшене
        critical_settings = [
            ('TELEGRAM_BOT_TOKEN', settings.TELEGRAM_BOT_TOKEN),
            ('SYRVE_SERVER_URL', settings.SYRVE_SERVER_URL),
            ('SYRVE_LOGIN', settings.SYRVE_LOGIN),
            ('SYRVE_PASSWORD', settings.SYRVE_PASSWORD),
        ]
        
        missing_vars = []
        for var_name, var_value in critical_settings:
            if not var_value or str(var_value).strip() == "":
                missing_vars.append(var_name)
                
        if missing_vars:
            pytest.fail(f"Missing critical configuration variables: {missing_vars}")


def run_deployment_tests():
    """Запуск всех тестов готовности к деплою."""
    print("🚀 Проверка готовности к деплою на сервер")
    print("=" * 60)
    
    # Запуск тестов
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    
    if exit_code == 0:
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система готова к деплою!")
        print("✅ Основные модули работают")
        print("✅ Улучшенный matcher функционирует")
        print("✅ Syrve интеграция настроена")
        print("✅ Мапинг продуктов обновлен") 
        print("✅ Конфигурация корректна")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ ТЕСТЫ НЕ ПРОЙДЕНЫ! Необходимо исправить ошибки перед деплоем!")
        print("=" * 60)
    
    return exit_code


if __name__ == "__main__":
    exit_code = run_deployment_tests()
    sys.exit(exit_code)