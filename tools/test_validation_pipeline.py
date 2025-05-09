#!/usr/bin/env python3
"""
Скрипт для демонстрации работы полного пайплайна валидации.
"""
import json
import argparse
import logging
import sys
import os
from decimal import Decimal
from pathlib import Path

# Добавляем корневую директорию в путь, чтобы импорты работали как в prod
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.validators.pipeline import ValidationPipeline

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Класс для сериализации Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def parse_args():
    parser = argparse.ArgumentParser(description='Тестирование полного пайплайна валидации')
    parser.add_argument('--input', '-i', required=True, help='Путь к JSON файлу с данными накладной')
    parser.add_argument('--output', '-o', help='Путь для сохранения результатов')
    parser.add_argument('--strict', '-s', action='store_true', help='Строгий режим валидации')
    parser.add_argument('--error-percent', '-e', type=float, default=1.0, 
                      help='Максимальный процент погрешности (по умолчанию 1.0)')
    return parser.parse_args()

def print_summary(result):
    """Выводит красивое резюме результатов валидации."""
    metadata = result.get('metadata', {})
    total_lines = metadata.get('total_lines', 0)
    total_issues = metadata.get('total_issues', 0)
    auto_fixed = metadata.get('auto_fixed', 0)
    lines_with_issues = metadata.get('lines_with_issues', 0)
    accuracy = metadata.get('accuracy', 0)
    
    print("\n" + "=" * 50)
    print("РЕЗУЛЬТАТЫ ВАЛИДАЦИИ НАКЛАДНОЙ")
    print("=" * 50)
    print(f"Всего строк: {total_lines}")
    print(f"Строк с проблемами: {lines_with_issues}")
    print(f"Всего проблем: {total_issues}")
    print(f"Автоматически исправлено: {auto_fixed}")
    print(f"Точность распознавания: {accuracy:.2%}")
    print("-" * 50)
    
    # Выводим проблемы по строкам
    issues_by_line = result.get('issues_by_line', {})
    if issues_by_line:
        print("\nДЕТАЛИ ПО СТРОКАМ:")
        for line_num, issues in sorted(issues_by_line.items()):
            print(f"\nСтрока {line_num}:")
            for issue in issues:
                issue_type = issue.get('type', 'UNKNOWN')
                severity = issue.get('severity', 'error')
                message = issue.get('message', '')
                fixed = ' [ИСПРАВЛЕНО]' if issue.get('fixed') else ''
                
                print(f"  - [{severity.upper()}] {issue_type}: {message}{fixed}")
    
    print("=" * 50)

def main():
    args = parse_args()
    
    # Проверяем наличие файла
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Файл не найден: {input_path}")
        return 1
    
    try:
        # Загружаем данные накладной
        with open(input_path, 'r', encoding='utf-8') as f:
            invoice_data = json.load(f)
        
        logger.info(f"Загружены данные накладной: {len(invoice_data.get('lines', []))} строк")
        
        # Создаем пайплайн валидации
        pipeline = ValidationPipeline(
            arithmetic_max_error=args.error_percent,
            strict_mode=args.strict
        )
        
        # Выполняем валидацию
        logger.info("Запуск полного пайплайна валидации...")
        result = pipeline.validate(invoice_data)
        
        # Выводим результаты
        print_summary(result)
        
        # Сохраняем результаты, если указан путь
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, cls=DecimalEncoder)
            logger.info(f"Результаты сохранены в {args.output}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 