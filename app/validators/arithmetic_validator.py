"""
Валидатор для проверки арифметических операций в накладной.

Проверяет корректность вычислений:
- цена × количество = сумма
- исправляет ошибки с лишними или потерянными нулями
- обрабатывает проблемы с десятичными разделителями
"""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ArithmeticValidator:
    """
    Валидатор для проверки и исправления арифметических ошибок в накладных.
    """

    def __init__(self, tolerance: float = 0.01, auto_fix: bool = True):
        """
        Инициализирует валидатор с настройками точности.

        Args:
            tolerance: Допустимая погрешность при сравнении чисел (в процентах)
            auto_fix: Автоматически исправлять обнаруженные ошибки
        """
        self.tolerance = tolerance
        self.auto_fix = auto_fix

    def validate(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет все строки накладной на арифметическую корректность.

        Args:
            invoice_data: Словарь с данными накладной

        Returns:
            Словарь с проверенными и исправленными данными
        """
        result = invoice_data.copy()
        lines = result.get("lines", [])
        issues = result.get("issues", [])

        # Проходим по всем строкам и проверяем
        for i, line in enumerate(lines):
            # Получаем значения полей (с проверкой типов)
            try:
                qty = self._parse_numeric(line.get("qty", 0))
                price = self._parse_numeric(line.get("price", 0))
                amount = self._parse_numeric(line.get("amount", 0))

                # Если какое-то из значений отсутствует или равно 0, но другие есть
                # пытаемся вычислить его
                if (
                    self._is_missing_or_zero(amount)
                    and not self._is_missing_or_zero(qty)
                    and not self._is_missing_or_zero(price)
                ):
                    # Вычисляем сумму, если она отсутствует
                    calculated_amount = qty * price
                    if self.auto_fix:
                        lines[i]["amount"] = calculated_amount
                        issues.append(
                            {
                                "type": "ARITHMETIC_FIX",
                                "line": i,
                                "field": "amount",
                                "message": f"Исправлена сумма: {qty} × {price} = {calculated_amount}",
                                "severity": "info",
                            }
                        )
                elif (
                    self._is_missing_or_zero(qty)
                    and not self._is_missing_or_zero(amount)
                    and not self._is_missing_or_zero(price)
                ):
                    # Вычисляем количество, если оно отсутствует и цена не равна 0
                    if price != 0:
                        calculated_qty = amount / price
                        if self.auto_fix:
                            lines[i]["qty"] = calculated_qty
                            issues.append(
                                {
                                    "type": "ARITHMETIC_FIX",
                                    "line": i,
                                    "field": "qty",
                                    "message": f"Исправлено количество: {amount} ÷ {price} = {calculated_qty}",
                                    "severity": "info",
                                }
                            )
                elif (
                    self._is_missing_or_zero(price)
                    and not self._is_missing_or_zero(amount)
                    and not self._is_missing_or_zero(qty)
                ):
                    # Вычисляем цену, если она отсутствует и количество не равно 0
                    if qty != 0:
                        calculated_price = amount / qty
                        if self.auto_fix:
                            lines[i]["price"] = calculated_price
                            issues.append(
                                {
                                    "type": "ARITHMETIC_FIX",
                                    "line": i,
                                    "field": "price",
                                    "message": f"Исправлена цена: {amount} ÷ {qty} = {calculated_price}",
                                    "severity": "info",
                                }
                            )
                else:
                    # Проверяем арифметическую точность
                    if (
                        not self._is_missing_or_zero(qty)
                        and not self._is_missing_or_zero(price)
                        and not self._is_missing_or_zero(amount)
                    ):
                        expected_amount = qty * price
                        if not self._is_close(expected_amount, amount):
                            # Проверка на ошибки с десятичными разделителями
                            fixed_values = self._try_fix_decimal_errors(qty, price, amount)
                            if fixed_values:
                                if self.auto_fix:
                                    lines[i]["qty"] = fixed_values["qty"]
                                    lines[i]["price"] = fixed_values["price"]
                                    lines[i]["amount"] = fixed_values["amount"]
                                    issues.append(
                                        {
                                            "type": "ARITHMETIC_FIX",
                                            "line": i,
                                            "field": "all",
                                            "message": f'Исправлены десятичные ошибки: {fixed_values["qty"]} × {fixed_values["price"]} = {fixed_values["amount"]}',
                                            "severity": "info",
                                        }
                                    )
                            else:
                                # Проверка на потерянные/лишние нули
                                fixed_values = self._try_fix_zero_errors(qty, price, amount)
                                if fixed_values:
                                    if self.auto_fix:
                                        lines[i]["qty"] = fixed_values["qty"]
                                        lines[i]["price"] = fixed_values["price"]
                                        lines[i]["amount"] = fixed_values["amount"]
                                        issues.append(
                                            {
                                                "type": "ARITHMETIC_FIX",
                                                "line": i,
                                                "field": "all",
                                                "message": f'Исправлены ошибки с нулями: {fixed_values["qty"]} × {fixed_values["price"]} = {fixed_values["amount"]}',
                                                "severity": "info",
                                            }
                                        )
                                else:
                                    # Если не смогли исправить, добавляем ошибку
                                    issues.append(
                                        {
                                            "type": "ARITHMETIC_ERROR",
                                            "line": i,
                                            "message": f"Ошибка в расчетах: {qty} × {price} = {amount}, ожидалось {expected_amount}",
                                            "severity": "warning",
                                        }
                                    )
            except Exception as e:
                logger.error(f"Ошибка при валидации строки {i}: {str(e)}")
                issues.append(
                    {
                        "type": "VALIDATION_ERROR",
                        "line": i,
                        "message": f"Ошибка при валидации: {str(e)}",
                        "severity": "error",
                    }
                )

        result["lines"] = lines
        result["issues"] = issues
        return result

    def _parse_numeric(self, value: Any) -> float:
        """
        Преобразует значение в число.
        Обрабатывает строки с разными форматами (запятая/точка).

        Args:
            value: Значение для преобразования

        Returns:
            Числовое значение
        """
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            # Удаляем все пробелы и символы тысяч
            cleaned = re.sub(r"[,\s]", "", value)
            # Заменяем запятую на точку, если это десятичный разделитель
            if "," in cleaned and "." not in cleaned:
                cleaned = cleaned.replace(",", ".")

            try:
                return float(cleaned)
            except ValueError:
                logger.warning(
                    f"Не удалось преобразовать '{value}' в число. Использую значение по умолчанию: 0"
                )
                return 0.0
        else:
            return 0.0

    def _is_close(self, a: float, b: float) -> bool:
        """
        Проверяет, близки ли два значения с учетом допуска.

        Args:
            a: Первое значение
            b: Второе значение

        Returns:
            True, если значения близки в пределах допуска
        """
        if a == 0 and b == 0:
            return True

        # Вычисляем относительную разницу
        relative_diff = abs(a - b) / max(abs(a), abs(b))
        return relative_diff <= self.tolerance

    def _is_missing_or_zero(self, value: float) -> bool:
        """
        Проверяет, отсутствует ли значение или равно 0.

        Args:
            value: Проверяемое значение

        Returns:
            True, если значение None, 0 или около 0
        """
        return value is None or abs(value) < 0.000001

    def _try_fix_decimal_errors(
        self, qty: float, price: float, amount: float
    ) -> Optional[Dict[str, float]]:
        """
        Пытается исправить ошибки с десятичными разделителями.

        Args:
            qty: Количество
            price: Цена
            amount: Сумма

        Returns:
            Словарь с исправленными значениями или None, если исправление не удалось
        """
        # Проверка на ошибку в price (потерянный десятичный разделитель)
        calculated_price = amount / qty if qty != 0 else 0
        if price > calculated_price * 10 and self._is_close(price / 10, calculated_price):
            return {"qty": qty, "price": price / 10, "amount": amount}
        elif price < calculated_price / 10 and self._is_close(price * 10, calculated_price):
            return {"qty": qty, "price": price * 10, "amount": amount}

        # Проверка на ошибку в amount (потерянный десятичный разделитель)
        calculated_amount = qty * price
        if amount > calculated_amount * 10 and self._is_close(amount / 10, calculated_amount):
            return {"qty": qty, "price": price, "amount": amount / 10}
        elif amount < calculated_amount / 10 and self._is_close(amount * 10, calculated_amount):
            return {"qty": qty, "price": price, "amount": amount * 10}

        return None

    def _try_fix_zero_errors(
        self, qty: float, price: float, amount: float
    ) -> Optional[Dict[str, float]]:
        """
        Пытается исправить ошибки с лишними или потерянными нулями.

        Args:
            qty: Количество
            price: Цена
            amount: Сумма

        Returns:
            Словарь с исправленными значениями или None, если исправление не удалось
        """
        # Проверка на потерянный ноль в цене
        calculated_amount = qty * (price * 10)
        if self._is_close(calculated_amount, amount):
            return {"qty": qty, "price": price * 10, "amount": amount}

        # Проверка на лишний ноль в цене
        calculated_amount = qty * (price / 10)
        if self._is_close(calculated_amount, amount):
            return {"qty": qty, "price": price / 10, "amount": amount}

        # Проверка на потерянный ноль в количестве
        calculated_amount = (qty * 10) * price
        if self._is_close(calculated_amount, amount):
            return {"qty": qty * 10, "price": price, "amount": amount}

        # Проверка на лишний ноль в количестве
        calculated_amount = (qty / 10) * price
        if self._is_close(calculated_amount, amount):
            return {"qty": qty / 10, "price": price, "amount": amount}

        # Проверка на потерянный ноль в сумме
        calculated_amount = qty * price
        if self._is_close(calculated_amount, amount * 10):
            return {"qty": qty, "price": price, "amount": amount * 10}

        # Проверка на лишний ноль в сумме
        if self._is_close(calculated_amount, amount / 10):
            return {"qty": qty, "price": price, "amount": amount / 10}

        return None
