#!/usr/bin/env python3
"""
Скрипт для демонстрации работы валидатора доменных бизнес-правил.
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

from app.validators.sanity import SanityValidator

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
    parser = argparse.ArgumentParser(description='Тестирование валидатора бизнес-правил')
    parser.add_argument('--input', '-i', required=True, help='Путь к JSON файлу с данными накладной')
    parser.add_argument('--output', '-o', help='Путь для сохранения результатов')
    parser.add_argument('--strict', '-s', action='store_true', help='Строгий режим валидации')
    return parser.parse_args()

def format_issue(issue):
    """Форматирует проблему для вывода в консоль."""
    line_num = issue.get('line', '?')
    issue_type = issue.get('type', 'UNKNOWN')
    severity = issue.get('severity', 'unknown')
    message = issue.get('message', '')
    fixed = 'ИСПРАВЛЕНО' if issue.get('fixed') else ''
    
    return f"[{severity.upper()}] Строка {line_num}: {issue_type} - {message} {fixed}"

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
        validator = SanityValidator(strict_mode=args.strict)
        
        # Валидируем данные
        result = validator.validate_invoice(invoice_data)
        
        # Выводим результаты
        issues = result.get('issues', [])
        auto_fixed = result.get('auto_fixed_count', 0)
        
        logger.info(f"Режим валидации: {'строгий' if args.strict else 'нестрогий'}")
        logger.info(f"Обнаружено проблем: {len(issues)}")
        logger.info(f"Автоматически исправлено: {auto_fixed}")
        
        if issues:
            logger.info("\nСписок проблем:")
            for issue in issues:
                logger.info(format_issue(issue))
        
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