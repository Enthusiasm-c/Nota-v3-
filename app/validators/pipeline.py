"""
Валидационный пайплайн для последовательной проверки и исправления ошибок.

Включает валидаторы:
1. ArithmeticValidator: проверяет арифметику (quantity × price = amount)
2. SanityValidator: проверяет бизнес-правила и здравый смысл
"""

import logging
from typing import Dict, List, Any, Union
import os
import json

from app.validators.arithmetic_validator import ArithmeticValidator
from app.validators.sanity_validator import SanityValidator

logger = logging.getLogger(__name__)

class ValidationPipeline:
    """
    Пайплайн валидации, который последовательно применяет
    несколько валидаторов к данным накладной.
    """
    
    def __init__(self):
        """
        Инициализирует пайплайн с набором валидаторов.
        """
        self.validators = [
            ArithmeticValidator(),
            SanityValidator()
        ]
    
    def validate(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Последовательно применяет все валидаторы к данным накладной.
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
                'valid_lines': 0,
                'accuracy': 1.0,  # 100% точность, т.к. нет ошибок валидации (только структуры)
                'status': 'invalid_structure'
            }
            return result
        
        # Последовательно применяем все валидаторы
        pipeline_result = result
        total_lines = len(pipeline_result.get('lines', []))
        error_lines = 0
        
        for validator in self.validators:
            try:
                pipeline_result = validator.validate(pipeline_result)
            except Exception as e:
                logger.error(f"Ошибка в валидаторе {validator.__class__.__name__}: {str(e)}", exc_info=True)
                issues = pipeline_result.get('issues', [])
                issues.append({
                    'type': 'VALIDATOR_ERROR',
                    'message': f"Ошибка валидации: {str(e)}",
                    'severity': 'error'
                })
                pipeline_result['issues'] = issues
        
        # Подсчитываем количество ошибок
        for issue in pipeline_result.get('issues', []):
            if issue.get('severity') == 'error' or issue.get('severity') == 'warning':
                error_lines += 1
        
        # Рассчитываем точность (% успешных строк)
        valid_lines = total_lines - error_lines
        accuracy = 1.0 if total_lines == 0 else valid_lines / total_lines
        
        # Добавляем метаданные о результатах валидации
        pipeline_result['metadata'] = {
            'total_lines': total_lines,
            'valid_lines': valid_lines,
            'accuracy': accuracy,
            'status': 'valid' if accuracy >= 0.9 else 'needs_review'
        }
        
        return pipeline_result 