from typing import Dict, List, Any
import logging
from app.validators.arithmetic import ArithmeticValidator
from app.validators.sanity import SanityValidator

logger = logging.getLogger(__name__)

class ValidationPipeline:
    """
    Пайплайн для последовательного выполнения нескольких валидаторов.
    
    Порядок выполнения:
    1. Арифметический валидатор (исправление числовых значений)
    2. Валидатор бизнес-правил (проверка доменной логики)
    """
    
    def __init__(self, arithmetic_max_error: float = 1.0, strict_mode: bool = False):
        """
        Инициализирует пайплайн валидации.
        
        Args:
            arithmetic_max_error: Максимальный процент ошибки для арифметического валидатора
            strict_mode: Строгий режим для валидатора бизнес-правил
        """
        self.arithmetic_validator = ArithmeticValidator(max_error_percent=arithmetic_max_error)
        self.sanity_validator = SanityValidator(strict_mode=strict_mode)
    
    def validate(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Последовательно применяет все валидаторы к данным накладной.
        
        Args:
            invoice_data: Данные накладной со списком строк (lines)
            
        Returns:
            Обновленные данные накладной с исправлениями и отметками о проблемах
        """
        # Проверка структуры
        result = invoice_data.copy()
        issues = result.get('issues', [])
        if not isinstance(invoice_data.get('lines'), list):
            issues.append({
                'type': 'STRUCTURE_ERROR',
                'message': "Поле 'lines' должно быть списком",
                'severity': 'error'
            })
            result['issues'] = issues
            result['metadata'] = {
                'total_lines': 0,
                'total_issues': len(issues),
                'auto_fixed': 0,
                'lines_with_issues': 0,
                'accuracy': 0
            }
            return result
        # Проверка строк
        for i, line in enumerate(invoice_data['lines']):
            if not isinstance(line, dict):
                issues.append({
                    'type': 'LINE_TYPE_ERROR',
                    'message': f'Строка {i+1} не является словарём',
                    'severity': 'error',
                    'line': i+1
                })
        if issues:
            result['issues'] = issues
            result['metadata'] = {
                'total_lines': len(invoice_data['lines']),
                'total_issues': len(issues),
                'auto_fixed': 0,
                'lines_with_issues': len(set([iss.get('line') for iss in issues if 'line' in iss])),
                'accuracy': 0
            }
            return result
        # Применяем арифметический валидатор (исправляет числовые ошибки)
        logger.info("Выполняем арифметическую валидацию...")
        result = self.arithmetic_validator.validate_invoice(invoice_data)
        
        # Применяем валидатор бизнес-правил (проверяет доменные правила)
        logger.info("Выполняем проверку бизнес-правил...")
        result = self.sanity_validator.validate_invoice(result)
        
        # Группируем проблемы по строкам для удобства анализа
        issues_by_line = {}
        for issue in result.get('issues', []):
            line_num = issue.get('line')
            if line_num:
                if line_num not in issues_by_line:
                    issues_by_line[line_num] = []
                issues_by_line[line_num].append(issue)
        
        # Добавляем поле issues_by_line
        result['issues_by_line'] = issues_by_line
        
        # Считаем общую статистику
        total_lines = len(result.get('lines', []))
        total_issues = len(result.get('issues', []))
        auto_fixed = result.get('auto_fixed_count', 0)
        
        # Вычисляем процент корректно распознанных строк
        if total_lines > 0:
            lines_with_issues = len(issues_by_line)
            correct_lines = total_lines - lines_with_issues + auto_fixed
            accuracy = correct_lines / total_lines
        else:
            accuracy = 0
        
        # Добавляем метаданные
        result['metadata'] = {
            'total_lines': total_lines,
            'total_issues': total_issues,
            'auto_fixed': auto_fixed,
            'lines_with_issues': len(issues_by_line),
            'accuracy': round(accuracy, 4)
        }
        
        return result 