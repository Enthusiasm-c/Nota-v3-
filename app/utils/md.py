import re
import logging

MDV2_SPECIALS = r'_\*\[\]\(\)~`>#+\-=|{}.!'

def escape_md(text: str, version=2) -> str:
    r"""
    Экранирует спецсимволы Telegram MarkdownV2. 
    Аргумент version для совместимости.
    """
    # Экранируем все спецсимволы из константы
    return re.sub(r'([' + MDV2_SPECIALS + r'])', r'\\\1', text)


def escape_v2(text: str) -> str:
    r"""
    Экранирует все спецсимволы Markdown V2, 
    сохраняя блоки кода нетронутыми.
    Для безопасной отправки в Telegram.
    """
    if text is None:
        return ""
    
    # Логирование для отладки
    logger = logging.getLogger("md")
    
    try:
        # Разделяем текст на части: код и не-код
        parts = []
        is_in_code_block = False
        lines = text.split('\n')
        current_block = []
        
        for line in lines:
            # Если встретили маркер начала/конца блока кода
            if line.strip() == '```':
                # Добавляем текущий блок с соответствующим экранированием
                if current_block:
                    joined_block = '\n'.join(current_block)
                    if not is_in_code_block:
                        # Экранируем текст вне блока кода
                        joined_block = escape_md(joined_block, version=2)
                    parts.append(joined_block)
                    current_block = []
                
                # Добавляем сам маркер блока кода (экранированный) и меняем флаг
                parts.append('```')
                is_in_code_block = not is_in_code_block
            else:
                current_block.append(line)
        
        # Добавляем оставшийся блок
        if current_block:
            joined_block = '\n'.join(current_block)
            if not is_in_code_block:
                # Экранируем текст вне блока кода
                joined_block = escape_md(joined_block, version=2)
            parts.append(joined_block)
        
        # Собираем всё вместе
        result = '\n'.join(parts)
        
        # Для обратной совместимости с предыдущими вызовами
        result = result.replace('\\```', '```')
        
        # Дополнительная проверка на экранирование всех спецсимволов
        if '.' in result and '\\.' not in result and not is_in_code_block:
            logger.warning("Found unescaped dots in the escaped text - manually escaping")
            result = result.replace('.', '\\.')
        
        # Проверка на экранирование других распространенных проблемных символов
        for char in ['#', '!', '+', '=', '|']:
            if char in result and f'\\{char}' not in result and '```' not in result:
                logger.warning(f"Found unescaped character '{char}' in text - manually escaping")
                result = result.replace(char, f'\\{char}')
        
        # Защита от двойного экранирования
        for char in MDV2_SPECIALS:
            double_escape = f'\\\\{char}'
            if double_escape in result:
                logger.warning(f"Found double-escaped character '{double_escape}' - fixing")
                result = result.replace(double_escape, f'\\{char}')
        
        return result
        
    except Exception as e:
        # В случае ошибки логируем и возвращаем безопасный текст
        if logger:
            logger.error(f"Error in escape_v2: {e}")
        
        # Безопасное возвращение: убираем все форматирование
        safe_text = re.sub(r'[^\w\s]', '', text)
        if len(safe_text) < 10:
            safe_text = "Error formatting message"
        
        return safe_text
