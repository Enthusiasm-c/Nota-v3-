"""
Тесты для проверки генерации XML-документов в соответствии с XSD-схемой Syrve API.
"""

import unittest
from decimal import Decimal
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock

from lxml import etree

from app.services.syrve_invoice_sender import (
    Invoice, InvoiceItem, SyrveClient
)


# Это упрощенная XSD-схема incomingInvoice для тестирования
# В реальной разработке рекомендуется использовать официальную XSD-схему от Syrve
EXAMPLE_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="document">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="items">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="item" maxOccurs="unbounded">
                                <xs:complexType>
                                    <xs:sequence>
                                        <xs:element name="productId" type="xs:string"/>
                                        <xs:element name="amount" type="xs:decimal"/>
                                        <xs:element name="price" type="xs:decimal"/>
                                        <xs:element name="sum" type="xs:decimal"/>
                                        <xs:element name="storeId" type="xs:string" minOccurs="0"/>
                                    </xs:sequence>
                                </xs:complexType>
                            </xs:element>
                        </xs:sequence>
                    </xs:complexType>
                </xs:element>
                <xs:element name="supplier" type="xs:string"/>
                <xs:element name="defaultStore" type="xs:string"/>
                <xs:element name="conception" type="xs:string" minOccurs="0"/>
                <xs:element name="documentNumber" type="xs:string" minOccurs="0"/>
                <xs:element name="dateIncoming" type="xs:date" minOccurs="0"/>
                <xs:element name="externalId" type="xs:string" minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
"""

# Создаем класс-наследник SyrveClient для тестирования
class MockSyrveClient(SyrveClient):
    """
    Мок-версия SyrveClient для тестов, которая не выполняет реальные HTTP-запросы.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Подменяем HTTP-клиент на мок-объект
        self.http = MagicMock()
    
    def get_token(self) -> str:
        """Переопределенный метод получения токена для тестов."""
        return "mock_token_for_tests"


class XMLSchemaTestCase(unittest.TestCase):
    """Тестирование генерации XML в соответствии с XSD-схемой."""

    def setUp(self):
        """Подготовка тестового окружения."""
        # Создаем тестовую схему
        self.schema_doc = etree.parse(BytesIO(EXAMPLE_XSD.encode('utf-8')))
        self.schema = etree.XMLSchema(self.schema_doc)
        
        # Создаем тестовый клиент
        self.client = MockSyrveClient(
            base_url="https://test.syrve.online",
            login="test_user",
            password_sha1="0e28ae04fce8ebabe057bb3144f1f05dac1c9206"
        )
        
        # Создаем тестовые данные
        self.supplier_id = "12345678-1234-1234-1234-123456789abc"
        self.store_id = "87654321-4321-4321-4321-cba987654321"
        self.conception_id = "abcdef12-3456-7890-abcd-ef1234567890"
        self.product_id = "11111111-2222-3333-4444-555555555555"
        
        # Создаем тестовый элемент инвойса
        self.item = InvoiceItem(
            num=1,
            product_id=self.product_id,
            amount=Decimal("10.5"),
            price=Decimal("100.00"),
            sum=Decimal("1050.00")
        )
        
        # Создаем тестовый инвойс с минимальными требуемыми полями
        self.invoice_minimal = Invoice(
            items=[self.item],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id
        )
        
        # Создаем тестовый инвойс со всеми полями
        self.invoice_full = Invoice(
            items=[
                self.item,
                InvoiceItem(
                    num=2,
                    product_id=self.product_id,
                    amount=Decimal("5.0"),
                    price=Decimal("200.00"),
                    sum=Decimal("1000.00"),
                    store_id=self.store_id
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id,
            conception_id=self.conception_id,
            document_number="TEST-20250101-12345",
            date_incoming=date(2025, 1, 1),
            external_id="external-id-12345"
        )

    def validate_xml(self, xml_string):
        """Проверяет XML на соответствие XSD-схеме."""
        try:
            doc = etree.parse(BytesIO(xml_string.encode('utf-8')))
            return self.schema.validate(doc)
        except Exception as e:
            return False, str(e)

    def test_minimal_invoice_xml(self):
        """Тестирует генерацию XML для минимального инвойса."""
        xml = self.client.generate_invoice_xml(self.invoice_minimal)
        is_valid = self.validate_xml(xml)
        self.assertTrue(is_valid, "Минимальный XML не соответствует схеме")
        
        # Проверяем наличие обязательных элементов
        self.assertIn("<items>", xml)
        self.assertIn("<item>", xml)
        self.assertIn("<productId>" + self.product_id + "</productId>", xml)
        self.assertIn("<amount>10.5</amount>", xml)
        self.assertIn("<price>100.00</price>", xml)
        self.assertIn("<sum>1050.00</sum>", xml)
        self.assertIn("<supplier>" + self.supplier_id + "</supplier>", xml)
        self.assertIn("<defaultStore>" + self.store_id + "</defaultStore>", xml)
        
        # Проверяем автоматическую генерацию externalId
        self.assertIn("<externalId>", xml)

    def test_full_invoice_xml(self):
        """Тестирует генерацию XML для полного инвойса со всеми полями."""
        xml = self.client.generate_invoice_xml(self.invoice_full)
        is_valid = self.validate_xml(xml)
        self.assertTrue(is_valid, "Полный XML не соответствует схеме")
        
        # Проверяем наличие всех элементов
        self.assertIn("<items>", xml)
        self.assertIn("<item>", xml)
        self.assertIn("<productId>" + self.product_id + "</productId>", xml)
        self.assertIn("<storeId>" + self.store_id + "</storeId>", xml)
        self.assertIn("<supplier>" + self.supplier_id + "</supplier>", xml)
        self.assertIn("<defaultStore>" + self.store_id + "</defaultStore>", xml)
        self.assertIn("<conception>" + self.conception_id + "</conception>", xml)
        self.assertIn("<documentNumber>TEST-20250101-12345</documentNumber>", xml)
        self.assertIn("<dateIncoming>2025-01-01</dateIncoming>", xml)
        self.assertIn("<externalId>external-id-12345</externalId>", xml)
        
        # Проверяем, что есть две позиции
        first_item_idx = xml.find("<item>")
        second_item_idx = xml.find("<item>", first_item_idx + 1)
        self.assertGreater(second_item_idx, first_item_idx, "Вторая позиция не найдена в XML")
    
    def test_xml_order(self):
        """Тестирует порядок элементов в XML документе."""
        xml = self.client.generate_invoice_xml(self.invoice_full)
        
        # Находим позиции элементов в XML
        items_pos = xml.find("<items>")
        supplier_pos = xml.find("<supplier>")
        default_store_pos = xml.find("<defaultStore>")
        conception_pos = xml.find("<conception>")
        document_number_pos = xml.find("<documentNumber>")
        date_incoming_pos = xml.find("<dateIncoming>")
        external_id_pos = xml.find("<externalId>")
        
        # Проверяем правильный порядок элементов
        self.assertLess(items_pos, supplier_pos, "items должен быть перед supplier")
        self.assertLess(supplier_pos, default_store_pos, "supplier должен быть перед defaultStore")
        self.assertLess(default_store_pos, conception_pos, "defaultStore должен быть перед conception")
        self.assertLess(conception_pos, document_number_pos, "conception должен быть перед documentNumber")
        self.assertLess(document_number_pos, date_incoming_pos, "documentNumber должен быть перед dateIncoming")
        self.assertLess(date_incoming_pos, external_id_pos, "dateIncoming должен быть перед externalId")


if __name__ == "__main__":
    unittest.main() 