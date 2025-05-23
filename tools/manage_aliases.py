#!/usr/bin/env python3
"""
Инструмент для управления алиасами продуктов в Nota AI.

Позволяет:
- Просматривать существующие алиасы
- Добавлять новые алиасы
- Удалять алиасы
- Обновлять алиасы
"""

import argparse
import csv
import os
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь импорта
sys.path.append(str(Path(__file__).parent.parent))

from app.alias import add_alias, read_aliases

DEFAULT_ALIAS_PATH = Path(__file__).parent.parent / "data" / "aliases.csv"


def list_aliases(args):
    """Список всех алиасов с возможностью фильтрации."""
    aliases = read_aliases(args.file)
    if not aliases:
        print("Алиасы не найдены.")
        return

    print(f"Всего алиасов: {len(aliases)}")
    print("\nИсходный текст -> ID продукта")
    print("-" * 50)

    # Сортировка
    sorted_aliases = sorted(aliases.items(), key=lambda x: x[1][1].lower())

    # Фильтрация по подстроке
    if args.filter:
        filter_text = args.filter.lower()
        sorted_aliases = [
            (alias, prod)
            for alias, prod in sorted_aliases
            if filter_text in alias or filter_text in prod[1].lower()
        ]

    # Вывод
    for alias, (product_id, orig_alias) in sorted_aliases:
        print(f"{orig_alias} -> {product_id}")


def add_new_alias(args):
    """Добавить новый алиас."""
    if not args.alias or not args.product_id:
        print("Ошибка: требуются --alias и --product_id")
        return

    # Добавляем алиас
    added = add_alias(args.alias, args.product_id, args.file)
    if added:
        print(f"Алиас '{args.alias}' для продукта '{args.product_id}' успешно добавлен.")
    else:
        print("Алиас уже существует.")


def delete_alias(args):
    """Удалить алиас."""
    if not args.alias:
        print("Ошибка: требуется --alias")
        return

    # Читаем алиасы
    aliases = read_aliases(args.file)
    alias_key = args.alias.strip().lower()

    if alias_key not in aliases:
        print(f"Алиас '{args.alias}' не найден.")
        return

    # Создаем временный файл с обновленными данными
    alias_path = Path(args.file)
    temp_path = alias_path.with_suffix(".tmp")

    with open(args.file, "r", encoding="utf-8") as infile, open(
        temp_path, "w", encoding="utf-8", newline=""
    ) as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        # Копируем заголовок
        header = next(reader, None)
        if header:
            writer.writerow(header)

        # Копируем все строки, кроме удаляемого алиаса
        for row in reader:
            if len(row) >= 2 and row[0].strip().lower() != alias_key:
                writer.writerow(row)

    # Заменяем исходный файл
    os.replace(temp_path, alias_path)
    print(f"Алиас '{args.alias}' успешно удален.")


def update_alias(args):
    """Обновить алиас."""
    if not args.alias or not args.product_id:
        print("Ошибка: требуются --alias и --product_id")
        return

    # Сначала удаляем алиас, если он существует
    delete_args = argparse.Namespace(alias=args.alias, file=args.file)
    delete_alias(delete_args)

    # Затем добавляем алиас с новым product_id
    add_args = argparse.Namespace(alias=args.alias, product_id=args.product_id, file=args.file)
    add_new_alias(add_args)


def main():
    parser = argparse.ArgumentParser(description="Управление алиасами продуктов")
    parser.add_argument("--file", default=str(DEFAULT_ALIAS_PATH), help="Путь к файлу алиасов")

    subparsers = parser.add_subparsers(dest="command", help="Команда")

    # Команда list
    list_parser = subparsers.add_parser("list", help="Показать алиасы")
    list_parser.add_argument("--filter", help="Фильтр по тексту")

    # Команда add
    add_parser = subparsers.add_parser("add", help="Добавить алиас")
    add_parser.add_argument("--alias", required=True, help="Текст алиаса")
    add_parser.add_argument("--product_id", required=True, help="ID продукта")

    # Команда delete
    delete_parser = subparsers.add_parser("delete", help="Удалить алиас")
    delete_parser.add_argument("--alias", required=True, help="Текст алиаса для удаления")

    # Команда update
    update_parser = subparsers.add_parser("update", help="Обновить алиас")
    update_parser.add_argument("--alias", required=True, help="Текст алиаса для обновления")
    update_parser.add_argument("--product_id", required=True, help="Новый ID продукта")

    args = parser.parse_args()

    # Проверяем существование файла и папки
    alias_path = Path(args.file)
    if not alias_path.parent.exists():
        alias_path.parent.mkdir(parents=True, exist_ok=True)

    # Вызываем соответствующую функцию
    if args.command == "list":
        list_aliases(args)
    elif args.command == "add":
        add_new_alias(args)
    elif args.command == "delete":
        delete_alias(args)
    elif args.command == "update":
        update_alias(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
