#!/usr/bin/env python3
"""
Пример использования автоматического преобразования единиц веса
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import ParsedData, Position
from app.postprocessing import postprocess_parsed_data


def main():
    """Демонстрация преобразования единиц веса"""
    
    # Создаем тестовую накладную с различными единицами веса
    invoice = ParsedData(
        supplier="Global Foods Ltd",
        date="2024-01-26",
        positions=[
            # Граммы - будет преобразовано в кг
            Position(
                name="Sugar",
                qty=2500,
                unit="g",
                price=0.05,  # цена за грамм
                total_price=125
            ),
            
            # Граммы - НЕ будет преобразовано (меньше 1000г)
            Position(
                name="Saffron",
                qty=50,
                unit="g",
                price=10.0,  # дорогая специя
                total_price=500
            ),
            
            # Тонны - будет преобразовано в кг
            Position(
                name="Wheat",
                qty=0.5,
                unit="t",
                price=300.0,  # цена за тонну
                total_price=150
            ),
            
            # Фунты - будет преобразовано в кг
            Position(
                name="Imported Cheese",
                qty=10,
                unit="lb",
                price=15.0,  # цена за фунт
                total_price=150
            ),
            
            # Килограммы - останется без изменений
            Position(
                name="Potatoes",
                qty=25,
                unit="kg",
                price=2.0,
                total_price=50
            ),
            
            # Миллиграммы - будет преобразовано в кг
            Position(
                name="Vitamin powder",
                qty=5_000_000,
                unit="mg",
                price=0.00001,  # цена за мг
                total_price=50
            )
        ],
        total_price=1025
    )
    
    print("=== Накладная ДО обработки ===")
    print(f"Поставщик: {invoice.supplier}")
    print(f"Дата: {invoice.date}")
    print("\nПозиции:")
    for i, pos in enumerate(invoice.positions, 1):
        print(f"{i}. {pos.name}: {pos.qty} {pos.unit} @ {pos.price} = {pos.total_price}")
    
    # Применяем постобработку
    processed = postprocess_parsed_data(invoice, "example-001")
    
    print("\n=== Накладная ПОСЛЕ обработки ===")
    print(f"Поставщик: {processed.supplier}")
    print(f"Дата: {processed.date}")
    print("\nПозиции:")
    for i, pos in enumerate(processed.positions, 1):
        print(f"{i}. {pos.name}: {pos.qty} {pos.unit} @ {pos.price} = {pos.total_price}")
    
    print("\n=== Преобразования веса ===")
    conversions = []
    no_conversions = []
    
    for i, (orig, proc) in enumerate(zip(invoice.positions, processed.positions), 1):
        if orig.unit != proc.unit:
            conversions.append(f"{i}. {orig.name}:")
            conversions.append(f"   Было: {orig.qty} {orig.unit} @ {orig.price}")
            conversions.append(f"   Стало: {proc.qty:.3f} {proc.unit} @ {proc.price:.2f}")
        elif orig.unit == proc.unit and orig.unit not in ['kg', 'pcs']:
            no_conversions.append(f"{i}. {orig.name}: не изменилось ({orig.qty} {orig.unit})")
    
    if conversions:
        print("\nПреобразованные:")
        for line in conversions:
            print(line)
    
    if no_conversions:
        print("\nНе преобразованные (маленькое количество):")
        for line in no_conversions:
            print(line)


if __name__ == "__main__":
    main()