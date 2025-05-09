#!/usr/bin/env python3
"""
Скрипт для демонстрации работы арифметического валидатора.
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

from app.validators.arithmetic import ArithmeticValidator

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
    parser = argparse.ArgumentParser(description='Тестирование арифметического валидатора')
    parser.add_argument('--input', '-i', required=True, help='Путь к JSON файлу с данными накладной')
    parser.add_argument('--output', '-o', help='Путь для сохранения результатов')
    parser.add_argument('--error-percent', '-e', type=float, default=1.0, 
                      help='Максимальный процент погрешности (по умолчанию 1.0)')
    return parser.parse_args()

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
        
        # Создаем валидатор
        validator = ArithmeticValidator(max_error_percent=args.error_percent)
        
        # Валидируем данные
        result = validator.validate_invoice(invoice_data)
        
        # Выводим результаты
        issues = result.get('issues', [])
        auto_fixed = result.get('auto_fixed_count', 0)
        
        logger.info(f"Обнаружено проблем: {len(issues)}")
        logger.info(f"Автоматически исправлено: {auto_fixed}")
        
        if issues:
            logger.info("\nСписок проблем:")
            for issue in issues:
                line_num = issue.get('line', '?')
                issue_type = issue.get('type', 'UNKNOWN')
                old_value = issue.get('old', '')
                fix = issue.get('fix', '')
                message = issue.get('message', '')
                
                if fix:
                    logger.info(f"Строка {line_num}: {issue_type} - исправлено с {old_value} на {fix}")
                else:
                    logger.info(f"Строка {line_num}: {issue_type} - {message}")
        
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