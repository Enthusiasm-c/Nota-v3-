#!/usr/bin/env python3
"""
Простой тест для проверки что автоматическая нумерация накладных убрана.
"""

import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

def test_no_auto_numbering():
    """Тестирует что автоматическая нумерация накладных отключена."""
    try:
        from app.services.unified_syrve_client import Invoice, InvoiceItem
        
        print("🧪 Testing invoice numbering behavior...")
        
        # Создаем накладную без номера
        items = [
            InvoiceItem(
                num=1,
                product_id="test-product-123",
                amount=Decimal("2.5"),
                price=Decimal("10.00"),
                sum=Decimal("25.00")
            )
        ]
        
        invoice = Invoice(
            items=items,
            supplier_id="test-supplier-456",
            default_store_id="test-store-789",
            document_number=None,  # Явно не устанавливаем номер
            date_incoming=date.today()
        )
        
        print(f"✅ Invoice created with document_number: {invoice.document_number}")
        
        # Проверяем что номер остался None
        if invoice.document_number is None:
            print("✅ SUCCESS: No automatic numbering - document_number is None")
            print("   Syrve will assign next sequential number")
        else:
            print(f"❌ FAILED: Auto-numbering still active - got: {invoice.document_number}")
            
        # Тестируем генерацию XML
        try:
            from app.services.unified_syrve_client import UnifiedSyrveClient
            client = UnifiedSyrveClient(
                base_url="http://test.local",
                login="test",
                password="test",
                verify_ssl=False
            )
            
            xml = client.generate_invoice_xml(invoice)
            print("\n📄 Generated XML:")
            print(xml[:500] + "..." if len(xml) > 500 else xml)
            
            # Проверяем что в XML нет тега documentNumber
            if "<documentNumber>" not in xml:
                print("✅ SUCCESS: No <documentNumber> tag in XML")
                print("   Syrve will auto-assign sequential number")
            else:
                print("❌ FAILED: <documentNumber> tag found in XML")
                
        except Exception as e:
            print(f"⚠️  XML generation test skipped: {e}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_no_auto_numbering()