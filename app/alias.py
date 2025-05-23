import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def read_aliases(path: str = "data/aliases.csv") -> Dict[str, tuple[str, str]]:
    # print(f"DEBUG: read_aliases called with path={path}")
    aliases: Dict[str, tuple[str, str]] = {}
    if not Path(path).exists():
        # print(f"DEBUG: Aliases file '{path}' does not exist")
        return aliases
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            # print(f"DEBUG: Read row from aliases: {row}")
            if len(row) >= 2:
                alias, pid = row[0], row[1]
                alias_l = alias.lower()
                aliases[alias_l] = (pid, alias)
    # print(f"DEBUG: Final aliases dict: {aliases}")
    return aliases


def add_alias(alias: str, product_id: str, path: str = "data/aliases.csv") -> bool:
    alias = alias.strip().lower()
    product_id = product_id.strip()
    aliases = read_aliases(path)
    if alias in aliases and aliases[alias][0] == product_id:
        return False  # Already exists
    write_header = not Path(path).exists() or Path(path).stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["alias", "product_id"])
        writer.writerow([alias, product_id])
        logger.info(f"Added alias '{alias}' for product_id '{product_id}' to '{path}'")
        f.flush()
        os.fsync(f.fileno())
    if Path(path).exists():
        # Проверка существования файла (удалена неиспользуемая переменная)
        with open(path, encoding="utf-8") as _:
            pass
    else:
        pass
    return True


def learn_from_invoice(
    positions: List[Dict], path: str = "data/aliases.csv"
) -> Tuple[int, List[str]]:
    """
    Автоматически добавляет алиасы из подтвержденной накладной.
    Используется после того, как пользователь подтвердил накладную.

    Args:
        positions: Список позиций накладной с сопоставлениями
        path: Путь к файлу алиасов

    Returns:
        Tuple[int, List[str]]: (количество добавленных алиасов, список алиасов)
    """
    added_count = 0
    added_aliases = []

    for pos in positions:
        # Проверяем, что это позиция с частичным совпадением
        if pos.get("status") == "partial":
            original_name = pos.get("name", "").strip()
            matched_product = pos.get("matched_product", None)

            if not original_name or not matched_product:
                continue

            product_id = ""
            if isinstance(matched_product, dict):
                product_id = matched_product.get("id", "")
            else:
                product_id = getattr(matched_product, "id", "")

            if not product_id:
                continue

            # Проверяем, содержит ли название цветовой префикс
            color_prefixes = ["green", "red", "yellow", "black", "white", "blue", "purple", "brown"]
            name_lower = original_name.lower()

            for color in color_prefixes:
                if name_lower.startswith(color + " "):
                    # Нашли цветовой префикс, добавляем алиас
                    if add_alias(original_name, product_id, path):
                        added_count += 1
                        added_aliases.append(original_name)
                        logger.info(
                            f"Автоматически добавлен алиас с цветовым префиксом: '{original_name}' -> '{product_id}'"
                        )
                    break

            # Проверяем на другие частичные совпадения, которые не являются цветовыми
            if "partial" in pos.get("match_reason", ""):
                if add_alias(original_name, product_id, path):
                    added_count += 1
                    added_aliases.append(original_name)
                    logger.info(
                        f"Автоматически добавлен алиас для частичного совпадения: '{original_name}' -> '{product_id}'"
                    )

    return added_count, added_aliases
