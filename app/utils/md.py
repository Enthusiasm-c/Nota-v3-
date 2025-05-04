import re
import logging

MDV2_SPECIALS = r"_\*\[\]\(\)~`>#+\-=|{}.!"


def escape_md(text: str, version=2) -> str:
    r"""
    Экранирует спецсимволы Telegram MarkdownV2.
    Аргумент version для совместимости.
    """
    # Экранируем все спецсимволы из константы
    return re.sub(r"([" + MDV2_SPECIALS + r"])", r"\\\1", text)


def escape_v2(text: str) -> str:
    r"""
    Экранирует все спецсимволы Markdown V2,
    сохраняя блоки кода нетронутыми.
    Для безопасной отправки в Telegram.
    """
    if text is None:
        return ""

    logger = logging.getLogger("md")

    try:
        # Обработка блоков кода и обычного текста отдельно
        result_parts = []
        is_in_code_block = False

        # Разбиваем текст на строки для обработки блоков кода
        lines = text.split("\n")
        current_block = []

        for line in lines:
            stripped_line = line.strip()

            # Обработка маркеров блоков кода
            if stripped_line == "```":
                # Обрабатываем накопленный блок текста
                if current_block:
                    block_text = "\n".join(current_block)
                    # Экранируем только текст вне блоков кода
                    if not is_in_code_block:
                        block_text = escape_md(block_text, version=2)
                    result_parts.append(block_text)
                    current_block = []

                # Добавляем маркер блока кода без экранирования
                result_parts.append("```")
                is_in_code_block = not is_in_code_block
            else:
                current_block.append(line)

        # Добавляем последний блок, если он есть
        if current_block:
            block_text = "\n".join(current_block)
            if not is_in_code_block:
                block_text = escape_md(block_text, version=2)
            result_parts.append(block_text)

        # Собираем текст обратно
        result = "\n".join(result_parts)

        # КРИТИЧНО: Проверяем и исправляем проблемные символы, которые часто вызывают ошибки
        problematic_chars = {
            ".": "\\.",
            "#": "\\#",
            "!": "\\!",
            "+": "\\+",
            "=": "\\=",
            "|": "\\|",
            "{": "\\{",
            "}": "\\}",
            "-": "\\-",
        }

        # Ищем части вне блоков кода для проверки неэкранированных символов
        parts = result.split("```")
        for i in range(0, len(parts), 2):  # Чётные индексы - части вне блоков кода
            if i < len(parts):
                for char, escaped in problematic_chars.items():
                    # Проверяем, есть ли символ, но нет его экранированной версии
                    if char in parts[i] and escaped not in parts[i]:
                        parts[i] = parts[i].replace(char, escaped)

                # Исправляем двойное экранирование
                for char in MDV2_SPECIALS:
                    double_escape = f"\\\\{char}"
                    if double_escape in parts[i]:
                        parts[i] = parts[i].replace(double_escape, f"\\{char}")

        # Собираем текст обратно с блоками кода
        final_result = ""
        for i, part in enumerate(parts):
            final_result += part
            if i < len(parts) - 1:
                final_result += "```"  # Добавляем маркеры блоков кода между частями

        # Проверка на потенциальные ошибки и логирование для диагностики
        if "```" in final_result:
            code_block_count = final_result.count("```")
            if code_block_count % 2 != 0:
                logger.warning(
                    f"Odd number of code block markers ({code_block_count}), formatting may be incorrect"
                )

        return final_result

    except Exception as e:
        # При ошибке возвращаем безопасный текст без форматирования
        logger.error(f"Error in escape_v2: {e}")

        # Удаляем все специальные символы для безопасности
        safe_text = re.sub(r"[^\w\s]", "", text)
        if len(safe_text) < 10:
            safe_text = "Error formatting message. Please try again."

        return safe_text
