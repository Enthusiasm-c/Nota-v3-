#!/usr/bin/env python3
"""
Скрипт для анализа настроек OCR и системного промпта
"""


def analyze_ocr_settings():
    """Анализирует настройки OCR"""
    print("=== АНАЛИЗ НАСТРОЕК OCR ===\n")

    # 1. Проверяем системный промпт
    try:
        from app.ocr_prompt import OCR_SYSTEM_PROMPT

        print("1. СИСТЕМНЫЙ ПРОМПТ OCR:")
        print("-" * 50)
        print(OCR_SYSTEM_PROMPT)
        print("-" * 50)

        # Анализируем промпт на предмет инструкций по ценам
        lines = OCR_SYSTEM_PROMPT.split("\n")
        price_related_lines = [
            line
            for line in lines
            if any(
                word in line.lower()
                for word in ["price", "цена", "currency", "валюта", "rp", "idr", "rupiah"]
            )
        ]

        print("\n2. ИНСТРУКЦИИ ПО ЦЕНАМ В ПРОМПТЕ:")
        if price_related_lines:
            for line in price_related_lines:
                print(f"  - {line.strip()}")
        else:
            print("  ❌ НЕ НАЙДЕНЫ специальные инструкции по обработке цен!")

    except ImportError as e:
        print(f"❌ Ошибка импорта промпта: {e}")

    # 2. Проверяем функцию парсинга чисел
    try:
        from app.ocr_helpers import parse_numeric_value

        print("\n3. ТЕСТИРОВАНИЕ ФУНКЦИИ ПАРСИНГА ЦЕН:")
        print("-" * 50)

        test_cases = [
            "16000",  # Базовый случай
            "16.000",  # Европейский формат
            "16,000",  # Американский формат
            "Rp 16000",  # С валютой
            "16K",  # С тысячами
            "16.000,00",  # Европейский с центами
            "1,234.56",  # Американский с центами
        ]

        for test_input in test_cases:
            result_int = parse_numeric_value(test_input, default=0, is_float=False)
            result_float = parse_numeric_value(test_input, default=0, is_float=True)
            print(f"  '{test_input}' -> int: {result_int}, float: {result_float}")

    except ImportError as e:
        print(f"❌ Ошибка импорта parse_numeric_value: {e}")

    # 3. Проверяем функцию форматирования цен
    try:
        from app.utils.formatters import format_price

        print("\n4. ТЕСТИРОВАНИЕ ФУНКЦИИ ФОРМАТИРОВАНИЯ ЦЕН:")
        print("-" * 50)

        test_values = [16000, 1234.5, 500000, 25.99, 0]

        for value in test_values:
            formatted = format_price(value, currency="", decimal_places=0)
            print(f"  {value} -> '{formatted}'")

    except ImportError as e:
        print(f"❌ Ошибка импорта format_price: {e}")

    # 4. Проверяем конфигурацию
    try:
        from app.config import settings

        print("\n5. НАСТРОЙКИ OCR:")
        print("-" * 50)

        ocr_attrs = [attr for attr in dir(settings) if "OCR" in attr.upper()]
        if ocr_attrs:
            for attr in ocr_attrs:
                print(f"  {attr}: {getattr(settings, attr, 'N/A')}")
        else:
            print("  ℹ️ Специальные настройки OCR не найдены")

        # Проверяем общие настройки
        general_attrs = ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]
        for attr in general_attrs:
            value = getattr(settings, attr, "N/A")
            if value and value != "N/A":
                masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                print(f"  {attr}: {masked}")

    except ImportError as e:
        print(f"❌ Ошибка импорта settings: {e}")


if __name__ == "__main__":
    analyze_ocr_settings()
