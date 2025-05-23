"""
Тесты для парсера команд изменения даты.
"""

import unittest

from app.parsers.date_parser import find_date_in_text, parse_date_command, parse_date_str


class DateParserTestCase(unittest.TestCase):
    """Тестирование парсера команд изменения даты."""

    def test_parse_date_str(self):
        """Проверка парсинга строк с датами в различных форматах."""
        # Формат DD.MM.YYYY
        result = parse_date_str("25.07.2024")
        self.assertIsNotNone(result)
        self.assertEqual(result["day"], 25)
        self.assertEqual(result["month"], 7)
        self.assertEqual(result["year"], 2024)
        self.assertEqual(result["date"], "2024-07-25")

        # Формат DD/MM/YYYY
        result = parse_date_str("01/12/2023")
        self.assertIsNotNone(result)
        self.assertEqual(result["date"], "2023-12-01")

        # Формат YYYY-MM-DD
        result = parse_date_str("2025-03-15")
        self.assertIsNotNone(result)
        self.assertEqual(result["day"], 15)
        self.assertEqual(result["month"], 3)
        self.assertEqual(result["year"], 2025)
        self.assertEqual(result["date"], "2025-03-15")

        # Невалидная дата
        result = parse_date_str("32.13.2022")
        self.assertIsNone(result)

        # Не дата вообще
        result = parse_date_str("hello world")
        self.assertIsNone(result)

    def test_find_date_in_text(self):
        """Проверка поиска даты в тексте."""
        # Простой текст с датой
        result = find_date_in_text("Дата накладной 10.05.2024")
        self.assertEqual(result, "2024-05-10")

        # Дата в середине текста
        result = find_date_in_text("Нужно изменить дату на 15.06.2023, пожалуйста")
        self.assertEqual(result, "2023-06-15")

        # ISO формат
        result = find_date_in_text("Дата 2023-07-01 в ISO формате")
        self.assertEqual(result, "2023-07-01")

        # Несколько дат (должна вернуться первая найденная)
        result = find_date_in_text("Даты 01.01.2022 и 31.12.2022")
        self.assertEqual(result, "2022-01-01")

        # Нет даты
        result = find_date_in_text("В этом тексте нет даты")
        self.assertIsNone(result)

    def test_russian_date_commands(self):
        """Проверка русских команд изменения даты."""
        # Прямая команда
        result = parse_date_command("дата 01.02.2023")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "set_date")
        self.assertEqual(result["value"], "2023-02-01")

        # Команда с глаголом
        result = parse_date_command("измени дату на 15.09.2024")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "set_date")
        self.assertEqual(result["value"], "2024-09-15")

        # Вариации
        result = parse_date_command("поменяй дату на 20/10/2025")
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "2025-10-20")

        result = parse_date_command("установить дату в 30.11.2022")
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "2022-11-30")

        # Ключевые слова, но не команда
        result = parse_date_command("проверь дату 05.07.2026")
        self.assertIsNotNone(result)  # Должна быть распознана по ключевым словам
        self.assertEqual(result["value"], "2026-07-05")

    def test_english_date_commands(self):
        """Проверка английских команд изменения даты."""
        # Прямая команда
        result = parse_date_command("date 01.02.2023")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "set_date")
        self.assertEqual(result["value"], "2023-02-01")

        # Команда с глаголом
        result = parse_date_command("change date to 15.09.2024")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "set_date")
        self.assertEqual(result["value"], "2024-09-15")

        # Вариации
        result = parse_date_command("set date to 20/10/2025")
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "2025-10-20")

        result = parse_date_command("date set to 30.11.2022")
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "2022-11-30")

        # ISO формат
        result = parse_date_command("change date to 2024-05-01")
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "2024-05-01")

    def test_negative_cases(self):
        """Проверка случаев, когда парсер не должен распознавать команды."""
        # Нет даты
        result = parse_date_command("измени дату")
        self.assertIsNone(result)

        # Нет ключевых слов даты
        result = parse_date_command("поменяй количество на 15.09.2024")
        self.assertIsNone(result)

        # Пустая строка
        result = parse_date_command("")
        self.assertIsNone(result)

        # Невалидная дата
        result = parse_date_command("дата 32.13.2022")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
