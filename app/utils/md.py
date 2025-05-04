import re
import logging
import html

MDV2_SPECIALS = r"_\*\[\]\(\)~`>#+\-=|{}.!"


def escape_html(text: str) -> str:
    """Экранирует спецсимволы для HTML (используется для Telegram HTML parse_mode)."""
    if text is None:
        return ""
    return html.escape(text)
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
