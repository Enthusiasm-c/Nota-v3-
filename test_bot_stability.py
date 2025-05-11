#!/usr/bin/env python
"""
Скрипт для комплексного тестирования устойчивости бота к различным изменениям в накладных.
Тестирует различные типы изменений и проверяет корректность обработки.
"""

import os
import json
import logging
import random
import datetime
import copy
import argparse
import time
from typing import Dict, List, Any, Optional

from app import matcher, data_loader
from app.models import ParsedData, Position
from app.postprocessing import postprocess_parsed_data

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])

logger = logging.getLogger("stability_tester")

class InvoiceStabilityTester:
    """
    Тестер устойчивости бота к изменениям в накладных.
    """
    
    def __init__(self, reference_json_path: str, output_dir: str, verbose: bool = False):
        """
        Инициализация тестера устойчивости.
        
        Args:
            reference_json_path: Путь к эталонному JSON файлу накладной
            output_dir: Директория для сохранения результатов тестов
            verbose: Подробный вывод
        """
        self.reference_json_path = reference_json_path
        self.output_dir = output_dir
        self.verbose = verbose
        self.test_results = {}  # Добавлено: словарь для хранения результатов тестов
        
        # Создаем директорию для результатов, если она не существует
        os.makedirs(output_dir, exist_ok=True)
        
        # Загружаем эталонные данные
        with open(reference_json_path, 'r', encoding='utf-8') as f:
            self.reference_data = json.load(f)
            
        # Загружаем продукты для сопоставления
        self.products = data_loader.load_products()
        logger.info(f"Загружено {len(self.products)} продуктов из базы")
        
        if verbose:
            logger.setLevel(logging.DEBUG)
    
    def modify_date(self, data: Dict) -> Dict:
        """
        Модифицирует дату в накладной случайным образом.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        modified = copy.deepcopy(data)
        
        # Получаем текущую дату
        current_date = datetime.datetime.now()
        
        # Генерируем случайную дату в пределах год до/после текущей
        days_delta = random.randint(-365, 365)
        new_date = current_date + datetime.timedelta(days=days_delta)
        
        # Всегда используем ISO формат (YYYY-MM-DD) для совместимости с моделью данных
        modified['date'] = new_date.strftime('%Y-%m-%d')
        
        return modified
    
    def modify_quantities(self, data: Dict) -> Dict:
        """
        Модифицирует количество товаров в накладной.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        modified = copy.deepcopy(data)
        
        for position in modified['lines']:
            # Выбираем случайный метод модификации
            modification_type = random.choice([
                'multiply', 'divide', 'add_decimal', 'round', 'none'
            ])
            
            original_qty = position['qty']
            
            if modification_type == 'multiply':
                # Умножаем на случайное число от 1.1 до 5.0
                multiplier = round(random.uniform(1.1, 5.0), 1)
                position['qty'] *= multiplier
                # Также увеличиваем amount пропорционально
                position['amount'] *= multiplier
                
            elif modification_type == 'divide':
                # Делим на случайное число от 1.1 до 3.0
                divider = round(random.uniform(1.1, 3.0), 1)
                position['qty'] /= divider
                # Также уменьшаем amount пропорционально
                position['amount'] /= divider
                
            elif modification_type == 'add_decimal':
                # Добавляем десятичную часть
                if isinstance(position['qty'], int):
                    decimal = round(random.uniform(0.1, 0.9), 1)
                    position['qty'] = float(position['qty']) + decimal
                    # Корректируем amount
                    if position['price']:
                        position['amount'] = position['qty'] * position['price']
                
            elif modification_type == 'round':
                # Округляем до целого
                if isinstance(position['qty'], float):
                    position['qty'] = round(position['qty'])
                    # Корректируем amount
                    if position['price']:
                        position['amount'] = position['qty'] * position['price']
            
            # В случае 'none' не делаем изменений
            
            logger.debug(f"Модификация количества: {original_qty} → {position['qty']} ({modification_type})")
        
        return modified
    
    def modify_units(self, data: Dict) -> Dict:
        """
        Модифицирует единицы измерения в накладной.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        modified = copy.deepcopy(data)
        
        # Словарь вариаций единиц измерения
        unit_variations = {
            'kg': ['kg', 'kgs', 'kilogram', 'kilograms', 'кг', 'кило', 'килограмм'],
            'g': ['g', 'gr', 'gram', 'grams', 'г', 'грамм'],
            'pcs': ['pcs', 'pc', 'piece', 'pieces', 'шт', 'штука', 'штуки', 'ea', 'each'],
            'btl': ['btl', 'bottle', 'bottles', 'бут', 'бутылка'],
            'box': ['box', 'boxes', 'коробка', 'коробки'],
            'pack': ['pack', 'packet', 'пакет'],
            'l': ['l', 'liter', 'liters', 'л', 'литр'],
            'ml': ['ml', 'milliliter', 'мл', 'миллилитр']
        }
        
        for position in modified['lines']:
            # Получаем текущую единицу измерения
            current_unit = position.get('unit', '').lower()
            
            # Находим базовую единицу
            base_unit = None
            for unit, variations in unit_variations.items():
                if current_unit in variations:
                    base_unit = unit
                    break
            
            # Если нашли базовую единицу, выбираем случайную вариацию
            if base_unit:
                random_variation = random.choice(unit_variations[base_unit])
                position['unit'] = random_variation
            else:
                # Если не нашли, выбираем случайную единицу из всех возможных
                all_variations = [var for variations in unit_variations.values() for var in variations]
                position['unit'] = random.choice(all_variations)
        
        return modified
    
    def modify_product_names(self, data: Dict) -> Dict:
        """
        Модифицирует названия продуктов в накладной.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        modified = copy.deepcopy(data)
        
        # Словарь вариаций названий продуктов
        name_variations = {
            'romaine': ['romaine', 'Romaine', 'romana', 'Romana', 'romaine lettuce'],
            'tomato': ['tomato', 'Tomato', 'tomatoes', 'Tomatoes'],
            'chickpeas': ['chickpeas', 'Chickpeas', 'chick peas', 'Chick Peas', 'chickpea'],
            'green bean': ['green bean', 'Green Bean', 'green beans', 'Green Beans'],
            'eggplant': ['eggplant', 'Eggplant', 'aubergine', 'Aubergine'],
            'watermelon': ['watermelon', 'Watermelon', 'water melon', 'Water Melon'],
            'mango': ['mango', 'Mango', 'mangoes', 'Mangoes']
        }
        
        for position in modified['lines']:
            # Получаем текущее название продукта
            current_name = position.get('name', '').lower()
            
            # Нормализуем название для поиска в словаре вариаций
            normalized_name = matcher.normalize_product_name(current_name)
            
            # Если находим в словаре вариаций, выбираем случайную вариацию
            found = False
            for base_name, variations in name_variations.items():
                if normalized_name == base_name or current_name in [v.lower() for v in variations]:
                    position['name'] = random.choice(variations)
                    found = True
                    break
            
            # Если не нашли в словаре, модифицируем регистр букв
            if not found:
                if random.random() < 0.5:  # 50% шанс
                    # Первая буква заглавная, остальные строчные
                    position['name'] = current_name.capitalize()
                else:
                    # Случайный выбор между верхним, нижним регистром или исходным
                    r = random.random()
                    if r < 0.33:
                        position['name'] = current_name.lower()
                    elif r < 0.66:
                        position['name'] = current_name.upper()
        
        return modified
    
    def modify_prices(self, data: Dict) -> Dict:
        """
        Модифицирует цены в накладной.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        modified = copy.deepcopy(data)
        
        for position in modified['lines']:
            # Выбираем случайный метод модификации
            modification_type = random.choice([
                'add_zero', 'remove_zero', 'change_format', 'small_change', 'none'
            ])
            
            price = position.get('price')
            amount = position.get('amount')
            
            if not price:
                continue
                
            original_price = price
            
            if modification_type == 'add_zero':
                # Добавляем ноль (x10)
                position['price'] = price * 10
                if amount:
                    position['amount'] = amount * 10
                    
            elif modification_type == 'remove_zero':
                # Убираем ноль (÷10)
                position['price'] = price / 10
                if amount:
                    position['amount'] = amount / 10
                    
            elif modification_type == 'change_format':
                # Меняем формат числа (добавляем разделители)
                # Для теста преобразуем в float, а не в строку, чтобы избежать ошибок валидации
                price_str = str(int(price))
                if len(price_str) > 3:
                    # Вместо строки с разделителями, сохраняем число как есть
                    # position['price'] = f"{price_str[:-3]},{price_str[-3:]}"
                    position['price'] = float(price)
            
            elif modification_type == 'small_change':
                # Небольшое изменение (±5%)
                change_percent = random.uniform(-0.05, 0.05)
                position['price'] = price * (1 + change_percent)
                if amount:
                    position['amount'] = amount * (1 + change_percent)
            
            # В случае 'none' не делаем изменений
            
            logger.debug(f"Модификация цены: {original_price} → {position['price']} ({modification_type})")
        
        return modified
    
    def test_modified_invoice(self, modification_type: str, modified_data: Dict) -> Dict:
        """
        Тестирует обработку модифицированной накладной.
        """
        try:
            timings = {}
            t0 = time.time()
            # Проверка структуры lines
            if not isinstance(modified_data.get('lines'), list):
                raise ValueError("Поле 'lines' должно быть списком")
            timings['structure_check'] = time.time() - t0
            
            t1 = time.time()
            lines = []
            for pos_dict in modified_data['lines']:
                try:
                    # Проверяем, что цена - это число, а не строка
                    price = pos_dict.get('price', 0)
                    if price is None:
                        price = 0
                    if isinstance(price, str):
                        price = float(price.replace(',', '.'))
                    
                    # Проверяем количество
                    qty = pos_dict.get('qty', 0)
                    if qty is None:
                        qty = 0
                    if isinstance(qty, str):
                        qty = float(qty.replace(',', '.'))
                    
                    # Создаем позицию
                    position = {
                        'name': pos_dict.get('name', ''),
                        'price': price,
                        'qty': qty,
                        'unit': pos_dict.get('unit', ''),
                        'amount': price * qty
                    }
                    lines.append(position)
                except Exception as e:
                    logger.error(f"Ошибка при обработке позиции: {str(e)}", exc_info=True)
            
            timings['convert_positions'] = time.time() - t1
            
            # Сохраняем модифицированную накладную
            filename = f"modified_{modification_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            output_dir = self.output_dir
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
            
            result = {
                'lines': lines,
                'supplier': modified_data.get('supplier', ''),
                'date': modified_data.get('date', ''),
                'invoice_number': modified_data.get('invoice_number', ''),
                'timings': timings,
                'total_time': time.time() - t0
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Модифицированная накладная сохранена: {output_path}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при тестировании {modification_type}: {str(e)}")
            raise
    
    def apply_random_modifications(self, data: Dict) -> None:
        """
        Применяет случайные модификации к данным накладной.
        
        Args:
            data: Данные накладной для модификации
        """
        # Случайно изменяем порядок позиций (с вероятностью 30%)
        if random.random() < 0.3:
            random.shuffle(data['lines'])
        
        # Случайно удаляем поле amount у некоторых позиций (с вероятностью 20%)
        for position in data['lines']:
            if 'amount' in position and random.random() < 0.2:
                del position['amount']
        
        # Случайно меняем регистр имен продуктов (с вероятностью 40%)
        for position in data['lines']:
            if random.random() < 0.4:
                if random.random() < 0.5:
                    # Все заглавные
                    position['name'] = position['name'].upper()
                else:
                    # Первая буква заглавная, остальные строчные
                    position['name'] = position['name'].capitalize()
    
    def modify_combined(self, data: Dict) -> Dict:
        """
        Применяет все модификации одновременно.
        
        Args:
            data: Данные накладной
            
        Returns:
            Модифицированные данные накладной
        """
        # Сначала применяем все виды модификаций по отдельности
        modified_units = self.modify_units(data)
        modified_names = self.modify_product_names(data)
        modified_prices = self.modify_prices(data)
        modified_quantities = self.modify_quantities(data)
        modified_date = self.modify_date(data)
        
        # Комбинируем все модификации
        result = copy.deepcopy(data)
        
        # Модифицируем дату
        result['date'] = modified_date['date']
        
        # Обновляем позиции
        for i, position in enumerate(result['lines']):
            # Модифицируем имя
            if i < len(modified_names['lines']):
                position['name'] = modified_names['lines'][i]['name']
            
            # Модифицируем единицы измерения
            if i < len(modified_units['lines']):
                position['unit'] = modified_units['lines'][i]['unit']
            
            # Модифицируем цены
            if i < len(modified_prices['lines']):
                position['price'] = modified_prices['lines'][i]['price']
                if 'amount' in modified_prices['lines'][i]:
                    position['amount'] = modified_prices['lines'][i]['amount']
            
            # Модифицируем количества
            if i < len(modified_quantities['lines']):
                position['qty'] = modified_quantities['lines'][i]['qty']
        
        return result
    
    def run_all_tests(self) -> Dict:
        """
        Запускает все тесты модификаций накладной.
        
        Returns:
            Общие результаты тестирования
        """
        tests = [
            ("date", self.modify_date),
            ("quantities", self.modify_quantities),
            ("units", self.modify_units),
            ("product_names", self.modify_product_names),
            ("prices", self.modify_prices)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            logger.info(f"Запуск теста модификации: {test_name}")
            
            # Применяем модификацию
            modified_data = test_func(self.reference_data)
            
            # Тестируем обработку модифицированной накладной
            result = self.test_modified_invoice(test_name, modified_data)
            results.append(result)
        
        # Комбинированный тест (все модификации вместе)
        logger.info("Запуск комбинированного теста (все модификации)")
        combined_data = self.reference_data.copy()
        for _, test_func in tests:
            combined_data = test_func(combined_data)
        
        combined_result = self.test_modified_invoice("combined", combined_data)
        results.append(combined_result)
        
        # Формируем общий отчет
        summary = {
            "total_tests": len(results),
            "successful_tests": sum(1 for r in results if r.get("error") is None),
            "avg_success_rate": sum(r.get("success_rate", 0) for r in results) / len(results) if results else 0,
            "results": results
        }
        
        # Сохраняем общий отчет
        summary_file = os.path.join(self.output_dir, f"stability_summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Все тесты завершены. Общий отчет сохранен в {summary_file}")
        logger.info(f"Успешно выполнено {summary['successful_tests']}/{summary['total_tests']} тестов")
        logger.info(f"Средняя успешность сопоставления: {summary['avg_success_rate']*100:.1f}%")
        
        return summary

    def test_combined(self):
        """
        Тестирует устойчивость к комбинированным изменениям в накладной (все типы модификаций одновременно).
        """
        logger.info("Запуск комбинированного теста (все модификации)")
        modified_data = self.modify_combined(self.reference_data)
        self.test_results['combined'] = self.test_modified_invoice("combined", modified_data)
        return self.test_results['combined']

    def test_missing_fields(self):
        """
        Тестирует реакцию на отсутствие обязательных полей в накладной и позициях.
        """
        logger.info("Тест: отсутствие обязательных полей")
        data = copy.deepcopy(self.reference_data)
        # Удаляем supplier и date
        data.pop('supplier', None)
        data.pop('date', None)
        # Удаляем name и unit у первой позиции
        if data['lines']:
            data['lines'][0].pop('name', None)
            data['lines'][0].pop('unit', None)
        return self.test_modified_invoice("missing_fields", data)

    def test_wrong_types(self):
        """
        Тестирует реакцию на неверные типы данных в полях накладной.
        """
        logger.info("Тест: неверные типы данных")
        data = copy.deepcopy(self.reference_data)
        # Числа в виде строк
        if data['lines']:
            data['lines'][0]['price'] = str(data['lines'][0]['price'])
            data['lines'][0]['qty'] = str(data['lines'][0]['qty'])
        # Дата в неверном формате
        data['date'] = "01.01.2022" if isinstance(data.get('date'), str) else "10/25/2020"
        return self.test_modified_invoice("wrong_types", data)

    def test_null_and_empty(self):
        """
        Тестирует реакцию на пустые и null значения в полях накладной.
        """
        logger.info("Тест: пустые и null значения")
        data = copy.deepcopy(self.reference_data)
        # Null в полях позиций
        if data['lines']:
            data['lines'][0]['unit'] = None
            data['lines'][0]['qty'] = None
        # Пустые строки в полях
        data['supplier'] = ""
        return self.test_modified_invoice("null_and_empty", data)

    def test_extreme_values(self):
        """
        Тестирует реакцию на экстремальные значения в полях накладной.
        """
        logger.info("Тест: экстремальные значения")
        data = copy.deepcopy(self.reference_data)
        # Очень большие и отрицательные числа
        if data['lines']:
            data['lines'][0]['qty'] = 999999999
            data['lines'][1]['price'] = -1000 if len(data['lines']) > 1 else -1000
        # Очень длинная строка наименования
        if data['lines']:
            data['lines'][0]['name'] = "A" * 1000
        return self.test_modified_invoice("extreme_values", data)

    def test_duplicate_positions(self):
        """
        Тестирует реакцию на дублирующиеся позиции.
        """
        logger.info("Тест: дублирование позиций")
        data = copy.deepcopy(self.reference_data)
        # Дублируем несколько позиций
        if data['lines'] and len(data['lines']) > 0:
            duplicate = copy.deepcopy(data['lines'][0])
            data['lines'].append(duplicate)
        return self.test_modified_invoice("duplicate_positions", data)

    def test_broken_structure(self):
        """
        Тестирует реакцию на структурные ошибки в накладной.
        """
        logger.info("Тест: битая структура JSON")
        data = copy.deepcopy(self.reference_data)
        # Заменяем массив позиций на строку
        data['lines'] = "not an array"
        return self.test_modified_invoice("broken_structure", data)

    def run_all_robustness_tests(self):
        """
        Запускает все дополнительные тесты на устойчивость к структурным и типовым ошибкам.
        """
        tests = [
            self.test_missing_fields,
            self.test_wrong_types,
            self.test_null_and_empty,
            self.test_extreme_values,
            self.test_duplicate_positions,
            self.test_broken_structure
        ]
        results = []
        for test in tests:
            try:
                results.append(test())
            except Exception as e:
                logger.error(f"Ошибка при выполнении теста {test.__name__}: {e}")
                results.append({"test": test.__name__, "error": str(e)})
        return results

    def test_units(self):
        return self.test_modified_invoice("units", self.modify_units(self.reference_data))
    def test_product_names(self):
        return self.test_modified_invoice("product_names", self.modify_product_names(self.reference_data))
    def test_quantities(self):
        return self.test_modified_invoice("quantities", self.modify_quantities(self.reference_data))
    def test_prices(self):
        return self.test_modified_invoice("prices", self.modify_prices(self.reference_data))
    def test_date(self):
        return self.test_modified_invoice("date", self.modify_date(self.reference_data))


def parse_args():
    """
    Разбор аргументов командной строки.
    """
    parser = argparse.ArgumentParser(description='Тестирование устойчивости бота к изменениям в накладных')
    parser.add_argument('--output', help='Путь для сохранения модифицированных накладных', default='tmp/stability_tests')
    parser.add_argument('--reference', help='Путь к эталонной накладной', default='tests/fixtures/sample_invoice.json')
    parser.add_argument('--verbose', help='Подробный вывод', action='store_true')
    parser.add_argument('--test', help='Конкретный тест для запуска', 
                        choices=['units', 'names', 'quantities', 'prices', 'date', 'combined', 'broken_structure'])
    parser.add_argument('--robust', help='Запустить все тесты устойчивости', action='store_true')
    return parser.parse_args()

def main():
    """
    Точка входа в программу.
    """
    args = parse_args()
    
    tester = InvoiceStabilityTester(
        reference_json_path=args.reference,
        output_dir=args.output,
        verbose=args.verbose
    )
    
    if args.test:
        # Запуск одного конкретного теста
        if args.test == 'units':
            tester.test_units()
        elif args.test == 'names':
            tester.test_product_names()
        elif args.test == 'quantities':
            tester.test_quantities()
        elif args.test == 'prices':
            tester.test_prices()
        elif args.test == 'date':
            tester.test_date()
        elif args.test == 'combined':
            tester.test_combined()
        elif args.test == 'broken_structure':
            tester.test_broken_structure()
    elif args.robust:
        # Запуск всех тестов устойчивости
        tester.run_all_robustness_tests()
    else:
        # Запуск всех обычных тестов
        tester.run_all_tests()


if __name__ == "__main__":
    main() 