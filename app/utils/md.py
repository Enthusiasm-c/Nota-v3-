import re

MDV2_SPECIALS = r'_\*\[\]\(\)~`>#+\-=|{}.!-'

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
    
    return result
