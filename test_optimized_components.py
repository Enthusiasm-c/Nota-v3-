#!/usr/bin/env python3
"""
Тестирование оптимизированных компонентов и проверка возможных багов
перед запуском бота.
"""

import sys
import os
import logging
from typing import Dict, Any, List, Optional
import unittest
import asyncio

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OptimizationTest(unittest.TestCase):
    """Тестирование основных оптимизированных компонентов"""
    
    def test_processing_guard(self):
        """Тестирование модуля защиты от повторной обработки"""
        from app.utils.processing_guard import (
            clear_all_locks,
            set_user_busy, 
            set_user_free, 
            check_user_busy,
            set_processing_photo,
            is_processing_photo
        )
        
        # Проверяем очистку всех блокировок
        clear_all_locks()
        logger.info("✅ clear_all_locks работает")
        
        # Тестируем установку и проверку блокировок
        async def test_locks():
            # Тестируем общую блокировку
            test_user_id = 12345
            await set_user_busy(test_user_id, "test_context")
            is_busy = await check_user_busy(test_user_id, "test_context")
            self.assertTrue(is_busy, "Пользователь должен быть помечен как занятый")
            
            # Тестируем освобождение
            await set_user_free(test_user_id, "test_context")
            is_busy = await check_user_busy(test_user_id, "test_context")
            self.assertFalse(is_busy, "Пользователь должен быть свободен после set_user_free")
            
            # Тестируем флаг обработки фото
            await set_processing_photo(test_user_id, True)
            self.assertTrue(await is_processing_photo(test_user_id), 
                           "Пользователь должен обрабатывать фото")
            
            await set_processing_photo(test_user_id, False)
            self.assertFalse(await is_processing_photo(test_user_id), 
                            "Пользователь не должен обрабатывать фото")
            
            # Проверяем работу таймаута
            # Установить блокировку с малым таймаутом в 0.1 сек
            await set_user_busy(test_user_id, "timeout_test", max_age=0.1)
            # Немного подождать
            await asyncio.sleep(0.2)
            # Таймаут должен истечь
            is_busy = await check_user_busy(test_user_id, "timeout_test")
            self.assertFalse(is_busy, "Блокировка должна быть автоматически снята по таймауту")
            
            logger.info("✅ Все тесты модуля processing_guard прошли успешно")

        # Запускаем асинхронный тест
        asyncio.run(test_locks())
        
    def test_cached_loader(self):
        """Тестирование модуля кеширования данных"""
        from app.utils.cached_loader import (
            cached_load_products,
            cached_load_data,
            clear_cache,
            get_cache_stats
        )
        
        # Тестовые данные
        test_data = [
            {"id": 1, "name": "test1"},
            {"id": 2, "name": "test2"},
        ]
        
        # Тестовая функция загрузки, которая всегда возвращает тестовые данные
        def test_loader(path):
            return test_data
        
        # Тестируем загрузку продуктов
        products = cached_load_products("test_path.csv", test_loader)
        self.assertEqual(len(products), 2, "Должно быть загружено 2 продукта")
        
        # Тестируем, что данные кешируются
        stats_before = get_cache_stats()
        products_again = cached_load_products("test_path.csv", test_loader)
        stats_after = get_cache_stats()
        
        self.assertEqual(stats_before["data_cache"]["size"], 
                         stats_after["data_cache"]["size"],
                        "Размер кеша не должен измениться при повторной загрузке")
        
        # Проверяем очистку кеша
        clear_cache()
        stats_cleared = get_cache_stats()
        self.assertEqual(stats_cleared["data_cache"]["size"], 0, 
                        "Кеш должен быть очищен")
        
        logger.info("✅ Все тесты модуля cached_loader прошли успешно")
        
    def test_string_cache(self):
        """Тестирование модуля кеширования строковых сравнений"""
        from app.utils.string_cache import (
            get_string_similarity_cached,
            set_string_similarity_cached,
            clear_string_cache,
            cached_string_similarity
        )
        
        # Тестируем базовые операции кеша
        s1, s2 = "test1", "test2"
        test_similarity = 0.75
        
        # Проверяем, что кеш изначально пуст
        self.assertIsNone(get_string_similarity_cached(s1, s2), 
                         "Кеш должен быть пустым изначально")
        
        # Добавляем значение и проверяем
        set_string_similarity_cached(s1, s2, test_similarity)
        self.assertEqual(get_string_similarity_cached(s1, s2), test_similarity,
                        "Значение должно быть сохранено в кеше")
        
        # Проверяем работу в обратном порядке строк
        self.assertEqual(get_string_similarity_cached(s2, s1), test_similarity,
                        "Кеш должен работать независимо от порядка строк")
        
        # Очищаем кеш и проверяем
        clear_string_cache()
        self.assertIsNone(get_string_similarity_cached(s1, s2),
                         "Кеш должен быть пустым после очистки")
        
        # Тестируем декоратор cached_string_similarity
        call_count = 0
        
        @cached_string_similarity
        def test_similarity_func(s1, s2):
            nonlocal call_count
            call_count += 1
            return 0.5
        
        # Вызываем функцию несколько раз с одними параметрами
        result1 = test_similarity_func("apple", "orange")
        result2 = test_similarity_func("apple", "orange")
        
        # Проверяем, что функция вызвана только один раз
        self.assertEqual(call_count, 1, 
                        "Декорированная функция должна вызываться только один раз для одинаковых аргументов")
        self.assertEqual(result1, result2, 
                        "Результаты кешированных вызовов должны совпадать")
        
        logger.info("✅ Все тесты модуля string_cache прошли успешно")
        
    def test_optimized_matcher(self):
        """Тестирование оптимизированного модуля сопоставления"""
        from app.utils.optimized_matcher import (
            normalize_product_name,
            calculate_string_similarity,
            async_match_positions
        )
        
        # Тестируем нормализацию имен продуктов
        tests = [
            ("Fresh tomatoes", "tomato"),
            ("TOMATOES", "tomato"),
            ("tomato organic", "tomato"),
            ("chickpeas", "chickpeas"),
            ("garbanzo beans", "chickpeas"),  # проверка синонимов
        ]
        
        for input_name, expected in tests:
            result = normalize_product_name(input_name)
            self.assertEqual(result, expected, 
                            f"Нормализация должна превратить '{input_name}' в '{expected}', получено '{result}'")
        
        # Тестируем сравнение строк
        similarity_tests = [
            ("apple", "apple", 1.0),  # идентичные строки
            ("", "", 1.0),  # пустые строки
            ("apple", "", 0.0),  # одна пустая строка
            ("apple", "orange", lambda x: x < 0.5),  # разные слова
            ("tomato", "tomatoes", lambda x: x > 0.8),  # единственное и множественное число
        ]
        
        for s1, s2, expected in similarity_tests:
            similarity = calculate_string_similarity(s1, s2)
            
            if callable(expected):
                self.assertTrue(expected(similarity), 
                              f"Сходство между '{s1}' и '{s2}' = {similarity} не удовлетворяет условию")
            else:
                self.assertAlmostEqual(similarity, expected, delta=0.001, 
                                     msg=f"Сходство между '{s1}' и '{s2}' должно быть {expected}")
        
        # Тестируем асинхронное сопоставление
        async def test_async_matching():
            positions = [
                {"name": "tomatoes", "qty": 2, "unit": "kg"},
                {"name": "unknown product", "qty": 1, "unit": "pc"}
            ]
            
            products = [
                {"id": 1, "name": "tomato"},
                {"id": 2, "name": "apple"},
                {"id": 3, "name": "orange"}
            ]
            
            results = await async_match_positions(positions, products)
            
            self.assertEqual(len(results), 2, "Должно быть обработано 2 позиции")
            self.assertEqual(results[0]["status"], "ok", "Помидоры должны быть распознаны")
            self.assertEqual(results[1]["status"], "unknown", "Неизвестный продукт не должен быть распознан")
        
        # Запускаем асинхронный тест
        asyncio.run(test_async_matching())
        
        logger.info("✅ Все тесты модуля optimized_matcher прошли успешно")
    
    def test_async_ocr(self):
        """Тестирование асинхронного OCR модуля (без реальных запросов)"""
        try:
            from app.utils.async_ocr import (
                close_http_session,
                get_current_session
            )
            
            # Проверяем, что модуль может быть импортирован и инициализирован
            session = get_current_session()
            self.assertIsNotNone(session, "HTTP сессия должна быть инициализирована")
            
            # Закрываем сессию
            async def close_test():
                await close_http_session()
                
            asyncio.run(close_test())
            logger.info("✅ Тесты модуля async_ocr прошли успешно")
        except ImportError as e:
            logger.warning(f"Модуль async_ocr не может быть импортирован: {e}")
            
    def test_timing_logger(self):
        """Тестирование модуля замера времени выполнения"""
        try:
            from app.utils.timing_logger import (
                async_timed,
                get_timing_stats
            )
            
            # Тестируем декоратор async_timed
            @async_timed(operation_name="test_op")
            async def test_function():
                await asyncio.sleep(0.1)
                return 123
                
            async def run_test():
                result = await test_function()
                self.assertEqual(result, 123, "Декоратор должен возвращать результат функции")
                
                # Получаем статистику
                stats = get_timing_stats()
                self.assertIn("test_op", str(stats), 
                             "Статистика должна содержать информацию о тестовой операции")
                
            # Запускаем асинхронный тест
            asyncio.run(run_test())
            logger.info("✅ Тесты модуля timing_logger прошли успешно")
        except ImportError as e:
            logger.warning(f"Модуль timing_logger не может быть импортирован: {e}")

def run_all_tests():
    """Запуск всех тестов"""
    logger.info("Запуск тестирования оптимизированных компонентов...")
    
    # Обнаруживаем и запускаем тесты
    suite = unittest.TestLoader().loadTestsFromTestCase(OptimizationTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    
    # Возвращаем код ошибки, если есть провальные тесты
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())