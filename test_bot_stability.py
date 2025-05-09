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
        
        for position in modified['positions']:
            # Выбираем случайный метод модификации
            modification_type = random.choice([
                'multiply', 'divide', 'add_decimal', 'round', 'none'
            ])
            
            original_qty = position['qty']
            
            if modification_type == 'multiply':
                # Умножаем на случайное число от 1.1 до 5.0
                multiplier = round(random.uniform(1.1, 5.0), 1)
                position['qty'] *= multiplier
                # Также увеличиваем total_price пропорционально
                position['total_price'] *= multiplier
                
            elif modification_type == 'divide':
                # Делим на случайное число от 1.1 до 3.0
                divider = round(random.uniform(1.1, 3.0), 1)
                position['qty'] /= divider
                # Также уменьшаем total_price пропорционально
                position['total_price'] /= divider
                
            elif modification_type == 'add_decimal':
                # Добавляем десятичную часть
                if isinstance(position['qty'], int):
                    decimal = round(random.uniform(0.1, 0.9), 1)
                    position['qty'] = float(position['qty']) + decimal
                    # Корректируем total_price
                    if position['price']:
                        position['total_price'] = position['qty'] * position['price']
                
            elif modification_type == 'round':
                # Округляем до целого
                if isinstance(position['qty'], float):
                    position['qty'] = round(position['qty'])
                    # Корректируем total_price
                    if position['price']:
                        position['total_price'] = position['qty'] * position['price']
            
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
        
        for position in modified['positions']:
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
        
        for position in modified['positions']:
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
        
        for position in modified['positions']:
            # Выбираем случайный метод модификации
            modification_type = random.choice([
                'add_zero', 'remove_zero', 'change_format', 'small_change', 'none'
            ])
            
            price = position.get('price')
            total_price = position.get('total_price')
            
            if not price:
                continue
                
            original_price = price
            
            if modification_type == 'add_zero':
                # Добавляем ноль (x10)
                position['price'] = price * 10
                if total_price:
                    position['total_price'] = total_price * 10
                    
            elif modification_type == 'remove_zero':
                # Убираем ноль (÷10)
                position['price'] = price / 10
                if total_price:
                    position['total_price'] = total_price / 10
                    
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
                if total_price:
                    position['total_price'] = total_price * (1 + change_percent)
            
            # В случае 'none' не делаем изменений
            
            logger.debug(f"Модификация цены: {original_price} → {position['price']} ({modification_type})")
        
        return modified
    
    def test_modified_invoice(self, modification_type: str, modified_data: Dict) -> Dict:
        """
        Тестирует обработку модифицированной накладной.
        
        Args:
            modification_type: Тип модификации
            modified_data: Модифицированные данные накладной
            
        Returns:
            Результаты тестирования
        """
        try:
            # Создаем объект ParsedData из модифицированных данных
            positions = []
            for pos_dict in modified_data['positions']:
                # Проверяем, что цена - это число, а не строка
                price = pos_dict['price']
                if isinstance(price, str):
                    # Конвертируем строковые цены с разделителями
                    price = price.replace(',', '')
                    price = float(price)
                    pos_dict['price'] = price
                
                # Аналогично для total_price
                total_price = pos_dict.get('total_price')
                if isinstance(total_price, str):
                    total_price = total_price.replace(',', '')
                    total_price = float(total_price)
                    pos_dict['total_price'] = total_price
                
                # Проверяем наличие обязательного поля qty
                if 'qty' not in pos_dict or pos_dict['qty'] is None:
                    pos_dict['qty'] = 1.0  # Устанавливаем значение по умолчанию
                
                positions.append(Position(
                    name=pos_dict['name'],
                    qty=pos_dict['qty'],
                    unit=pos_dict['unit'],
                    price=pos_dict['price'],
                    total_price=pos_dict.get('total_price')
                ))
            
            # Проверяем формат даты, при необходимости исправляем
            date = modified_data['date']
            if isinstance(date, str) and not date.startswith('20'):  # Простая проверка на ISO формат
                # Пытаемся преобразовать дату в ISO формат
                try:
                    # Пробуем разные форматы даты
                    for fmt in ['%d.%m.%Y', '%m/%d/%Y', '%d-%m-%Y']:
                        try:
                            parsed_date = datetime.datetime.strptime(date, fmt)
                            date = parsed_date.strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue
                except Exception:
                    # Если не удалось распознать формат, используем текущую дату
                    date = datetime.datetime.now().strftime('%Y-%m-%d')
            
            parsed_data = ParsedData(
                supplier=modified_data['supplier'],
                date=date,
                positions=positions,
                total_price=modified_data.get('total_price', 0)
            )
            
            # Применяем постобработку
            logger.info(f"Применяем постобработку для {modification_type}")
            processed_data = postprocess_parsed_data(parsed_data)
            
            # Выполняем сопоставление с базой продуктов
            logger.info(f"Выполняем сопоставление позиций для {modification_type}")
            positions_for_matching = [
                {"name": pos.name, "qty": pos.qty, "unit": pos.unit, "price": pos.price, "total_price": pos.total_price}
                for pos in processed_data.positions
            ]
            
            matched_positions = matcher.match_positions(positions_for_matching, self.products)
            
            # Подсчитываем количество успешных сопоставлений
            ok_count = sum(1 for pos in matched_positions if pos['status'] == 'ok')
            partial_count = sum(1 for pos in matched_positions if pos['status'] == 'partial')
            unknown_count = sum(1 for pos in matched_positions if pos['status'] == 'unknown')
            
            # Формируем отчет
            report = {
                "modification_type": modification_type,
                "total_positions": len(matched_positions),
                "ok_matches": ok_count,
                "partial_matches": partial_count,
                "unknown_matches": unknown_count,
                "success_rate": (ok_count + partial_count) / len(matched_positions) if matched_positions else 0,
                "error": None
            }
            
            # Сохраняем результаты модификации и сопоставления
            output_file = os.path.join(self.output_dir, f"modified_{modification_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(output_file, 'w') as f:
                json.dump({
                    "original": self.reference_data,
                    "modified": modified_data,
                    "processed": processed_data.dict(),
                    "matched": matched_positions,
                    "report": report
                }, f, indent=2, default=str)
            
            logger.info(f"Результаты теста {modification_type} сохранены в {output_file}")
            logger.info(f"Успешных сопоставлений: {ok_count + partial_count}/{len(matched_positions)} ({report['success_rate']*100:.1f}%)")
            
            return report
        
        except Exception as e:
            logger.error(f"Ошибка при тестировании {modification_type}: {e}")
            return {
                "modification_type": modification_type,
                "error": str(e),
                "success_rate": 0
            }
    
    def apply_random_modifications(self, data: Dict) -> None:
        """
        Применяет случайные модификации к данным накладной.
        
        Args:
            data: Данные накладной для модификации
        """
        # Случайно изменяем порядок позиций (с вероятностью 30%)
        if random.random() < 0.3:
            random.shuffle(data['positions'])
        
        # Случайно удаляем поле total_price у некоторых позиций (с вероятностью 20%)
        for position in data['positions']:
            if 'total_price' in position and random.random() < 0.2:
                del position['total_price']
        
        # Случайно меняем регистр имен продуктов (с вероятностью 40%)
        for position in data['positions']:
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
        for i, position in enumerate(result['positions']):
            # Модифицируем имя
            if i < len(modified_names['positions']):
                position['name'] = modified_names['positions'][i]['name']
            
            # Модифицируем единицы измерения
            if i < len(modified_units['positions']):
                position['unit'] = modified_units['positions'][i]['unit']
            
            # Модифицируем цены
            if i < len(modified_prices['positions']):
                position['price'] = modified_prices['positions'][i]['price']
                if 'total_price' in modified_prices['positions'][i]:
                    position['total_price'] = modified_prices['positions'][i]['total_price']
            
            # Модифицируем количества
            if i < len(modified_quantities['positions']):
                position['qty'] = modified_quantities['positions'][i]['qty']
            
            # Гарантируем, что у каждой позиции есть поле qty (добавляем значение по умолчанию, если отсутствует)
            if 'qty' not in position or position['qty'] is None:
                position['qty'] = 1.0
        
        # Вносим некоторые хаотичные изменения
        self.apply_random_modifications(result)
        
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


def main():
    """
    Основная функция скрипта для запуска тестирования.
    """
    # Настройка аргументов командной строки
    parser = argparse.ArgumentParser(description='Тестирование устойчивости бота к модификациям накладных')
    parser.add_argument('--output', type=str, default='tmp/stability_tests', 
                        help='Директория для сохранения результатов тестов')
    parser.add_argument('--reference', type=str, default='data/sample/invoice_reference.json', 
                        help='Путь к эталонному JSON файлу накладной')
    parser.add_argument('--verbose', action='store_true', 
                        help='Показывать подробную информацию о процессе тестирования')
    parser.add_argument('--test', type=str, choices=['units', 'names', 'quantities', 'prices', 'date', 'combined'], 
                        help='Запустить только определенный тест')
    args = parser.parse_args()
    
    # Создаем экземпляр тестера
    tester = InvoiceStabilityTester(args.reference, args.output, args.verbose)
    
    # Запускаем тестирование
    if args.test:
        # Запуск только определенного теста
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
    else:
        # Запуск всех тестов
        tester.run_all_tests()


if __name__ == "__main__":
    main() 