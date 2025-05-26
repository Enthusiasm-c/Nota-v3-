"""
Тесты для улучшенного модуля matcher с новым алгоритмом схожести.
"""

import pytest
from app.matcher import (
    calculate_string_similarity,
    fuzzy_find,
    match_positions,
    get_best_match,
    normalize_product_name
)


class TestImprovedMatcher:
    """Тесты для улучшенного алгоритма сопоставления."""

    def test_calculate_string_similarity_exact_match(self):
        """Тест точного совпадения."""
        assert calculate_string_similarity("mayo", "mayo") == 1.0
        assert calculate_string_similarity("chicken breast", "chicken breast") == 1.0

    def test_calculate_string_similarity_none_values(self):
        """Тест обработки None значений."""
        assert calculate_string_similarity(None, "mayo") == 0.0
        assert calculate_string_similarity("mayo", None) == 0.0
        assert calculate_string_similarity(None, None) == 0.0

    def test_calculate_string_similarity_partial_match(self):
        """Тест частичного совпадения (основная улучшенная функция)."""
        # Проверяем, что mayonnaise -> mayo теперь проходит по порогу 0.75
        score = calculate_string_similarity("mayonnaise", "mayo")
        assert score >= 0.75, f"Expected score >= 0.75, got {score}"
        
        # Другие случаи частичного совпадения
        assert calculate_string_similarity("chicken breast", "chicken") >= 0.75
        assert calculate_string_similarity("tomato sauce", "tomato") >= 0.75
        assert calculate_string_similarity("olive oil", "oil") >= 0.75

    def test_calculate_string_similarity_different_strings(self):
        """Тест для совершенно разных строк."""
        score = calculate_string_similarity("completely different", "words")
        assert score < 0.5, f"Expected score < 0.5 for different strings, got {score}"

    def test_calculate_string_similarity_case_insensitive(self):
        """Тест нечувствительности к регистру."""
        assert calculate_string_similarity("MAYO", "mayo") == 1.0
        assert calculate_string_similarity("Mayonnaise", "MAYO") >= 0.75

    def test_fuzzy_find_basic(self):
        """Тест базового поиска с fuzzy_find."""
        products = [
            {"id": "1", "name": "mayo", "alias": "mayo"},
            {"id": "2", "name": "chicken breast", "alias": "chicken"},
            {"id": "3", "name": "tomato sauce", "alias": "tomato"}
        ]
        
        # Тест поиска mayonnaise -> mayo
        results = fuzzy_find("mayonnaise", products, threshold=0.75)
        assert len(results) == 1
        assert results[0]["name"] == "mayo"
        assert results[0]["score"] >= 0.75

    def test_fuzzy_find_empty_inputs(self):
        """Тест обработки пустых входных данных."""
        products = [{"id": "1", "name": "mayo"}]
        
        assert fuzzy_find("", products) == []
        assert fuzzy_find("mayo", []) == []
        assert fuzzy_find("", []) == []

    def test_fuzzy_find_threshold(self):
        """Тест работы с порогом."""
        products = [
            {"id": "1", "name": "mayo"},
            {"id": "2", "name": "completely different"}
        ]
        
        # Высокий порог - только хорошие совпадения
        results = fuzzy_find("mayonnaise", products, threshold=0.75)
        assert len(results) == 1
        assert results[0]["name"] == "mayo"
        
        # Низкий порог - больше результатов
        results = fuzzy_find("mayonnaise", products, threshold=0.1)
        assert len(results) >= 1

    def test_match_positions(self):
        """Тест сопоставления позиций накладной с продуктами."""
        positions = [
            {"name": "mayonnaise", "qty": 1, "price": 100},
            {"name": "chicken breast", "qty": 2, "price": 200},
            {"name": "unknown product", "qty": 1, "price": 50}
        ]
        
        products = [
            {"id": "1", "name": "mayo", "alias": "mayo"},
            {"id": "2", "name": "chicken breast", "alias": "chicken"}
        ]
        
        results = match_positions(positions, products, threshold=0.75)
        
        assert len(results) == 3
        
        # Проверяем первую позицию (mayonnaise -> mayo)
        assert results[0]["status"] == "ok"
        assert results[0]["matched_name"] == "mayo"
        assert results[0]["id"] == "1"
        
        # Проверяем вторую позицию (точное совпадение)
        assert results[1]["status"] == "ok"
        assert results[1]["matched_name"] == "chicken breast"
        assert results[1]["id"] == "2"
        
        # Проверяем третью позицию (не найдено)
        assert results[2]["status"] == "unknown"
        assert results[2]["score"] == 0.0

    def test_get_best_match(self):
        """Тест поиска лучшего совпадения."""
        products = [
            {"id": "1", "name": "mayo"},
            {"id": "2", "name": "mayonnaise sauce"},
            {"id": "3", "name": "chicken"}
        ]
        
        best_match = get_best_match("mayonnaise", products, threshold=0.75)
        assert best_match is not None
        assert best_match["name"] in ["mayo", "mayonnaise sauce"]

    def test_normalize_product_name(self):
        """Тест нормализации названий продуктов."""
        assert normalize_product_name("  Mayo  ") == "mayo"
        assert normalize_product_name("Chicken-Breast") == "chicken-breast"
        assert normalize_product_name("") == ""
        assert normalize_product_name("   ") == ""

    def test_real_world_scenarios(self):
        """Тест реальных сценариев использования."""
        
        # Продукты из реальной базы
        products = [
            {"id": "mayo-id", "name": "mayo", "alias": "mayo"},
            {"id": "mozzarella-id", "name": "mozzarela", "alias": "mozzarella"},
            {"id": "chicken-id", "name": "chicken breast", "alias": "chicken"},
            {"id": "tomato-id", "name": "tomato sauce", "alias": "tomato"},
            {"id": "oil-id", "name": "olive oil", "alias": "oil"}
        ]
        
        # Тестовые запросы из накладных
        test_queries = [
            ("mayonnaise", "mayo-id"),
            ("mozzarella", "mozzarella-id"),
            ("chicken", "chicken-id"),
            ("tomato", "tomato-id"),
            ("oil", "oil-id")
        ]
        
        for query, expected_id in test_queries:
            results = fuzzy_find(query, products, threshold=0.75, limit=1)
            assert len(results) == 1, f"No match found for {query}"
            assert results[0]["id"] == expected_id, f"Wrong match for {query}: expected {expected_id}, got {results[0]['id']}"
            assert results[0]["score"] >= 0.75, f"Score too low for {query}: {results[0]['score']}"


class TestPerformance:
    """Тесты производительности для улучшенного алгоритма."""
    
    def test_similarity_calculation_performance(self):
        """Тест производительности расчета схожести."""
        import time
        
        # Подготавливаем тестовые данные
        queries = ["mayonnaise", "chicken breast", "tomato sauce"] * 100
        targets = ["mayo", "chicken", "tomato"] * 100
        
        start_time = time.time()
        
        for query, target in zip(queries, targets):
            calculate_string_similarity(query, target)
            
        end_time = time.time()
        
        # Проверяем, что 300 вычислений выполняются менее чем за 1 секунду
        execution_time = end_time - start_time
        assert execution_time < 1.0, f"Performance test failed: {execution_time:.3f}s for 300 calculations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])