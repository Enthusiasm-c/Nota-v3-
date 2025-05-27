#!/usr/bin/env python3
"""
Простой тест системы маппинга поставщиков без зависимостей.
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

def test_supplier_mapping():
    """Тестирует базовую функциональность маппинга поставщиков."""
    
    # Имитируем данные накладной
    test_invoices = [
        {"supplier": "7AM Bakers"},
        {"supplier": "ASkitchen"},
        {"supplier": "Unknown Supplier"},
        {"supplier": None},
        {}
    ]
    
    # Проверяем resolve_supplier_for_invoice
    try:
        from app.supplier_mapping import resolve_supplier_for_invoice
        
        print("🧪 Testing supplier resolution...")
        
        for i, invoice in enumerate(test_invoices, 1):
            supplier_guid = resolve_supplier_for_invoice(invoice)
            supplier_name = invoice.get('supplier', 'None')
            print(f"Test {i}: '{supplier_name}' -> {supplier_guid}")
            
        print("✅ Supplier mapping test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_supplier_mapping()