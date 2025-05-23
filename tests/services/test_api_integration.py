"""
Интеграционные тесты API Syrve с использованием мок-объектов.
"""

import unittest
from unittest.mock import patch
from decimal import Decimal
from datetime import date
import httpx
import responses

from app.services.syrve_invoice_sender import (
    Invoice, InvoiceItem, SyrveClient,
    InvoiceValidationError, InvoiceHTTPError, InvoiceAuthError
)


# Создаем класс-наследник SyrveClient для тестирования
class MockSyrveClient(SyrveClient):
    """
    Мок-версия SyrveClient для тестов, которая позволяет контролировать HTTP-запросы.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Сохраняем базовые параметры для использования в тестах
        self.mock_token = "token123456789"
        # Не создаем реальный HTTP-клиент
        self.http = None


class ApiIntegrationTestCase(unittest.TestCase):
    """Тестирование интеграции с API Syrve."""

    def setUp(self):
        """Подготовка тестового окружения."""
        # Создаем тестовые данные
        self.supplier_id = "12345678-1234-1234-1234-123456789abc"
        self.store_id = "87654321-4321-4321-4321-cba987654321"
        self.product_id = "11111111-2222-3333-4444-555555555555"
        self.unknown_product_id = "99999999-9999-9999-9999-999999999999"
        
        # Создаем тестовый клиент
        self.client = MockSyrveClient(
            base_url="https://test.syrve.online",
            login="test_user",
            password_sha1="0e28ae04fce8ebabe057bb3144f1f05dac1c9206"
        )
        
        # Создаем тестовые инвойсы
        self.valid_invoice = Invoice(
            items=[
                InvoiceItem(
                    num=1,
                    product_id=self.product_id,
                    amount=Decimal("10.5"),
                    price=Decimal("100.00"),
                    sum=Decimal("1050.00")
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id,
            date_incoming=date(2025, 1, 1)
        )
        
        self.invalid_invoice = Invoice(
            items=[
                InvoiceItem(
                    num=1,
                    product_id=self.unknown_product_id,
                    amount=Decimal("10.5"),
                    price=Decimal("100.00"),
                    sum=Decimal("1050.00")
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id,
            date_incoming=date(2025, 1, 1)
        )
        
        # Подготавливаем тестовые ответы API
        self.token_response = "test_token_12345"
        
        # Успешный ответ с номером документа
        self.success_response = '''<?xml version="1.0" encoding="UTF-8"?>
<documentValidationResult>
    <valid>true</valid>
    <documentNumber>SYRVE-20250101-001</documentNumber>
</documentValidationResult>'''
        
        # Ответ с ошибкой валидации
        self.invalid_response = '''<?xml version="1.0" encoding="UTF-8"?>
<documentValidationResult>
    <valid>false</valid>
    <errorMessage>Unknown product id: {}</errorMessage>
</documentValidationResult>'''.format(self.unknown_product_id)

    @responses.activate
    def test_token_request(self):
        """Тестирует запрос аутентификационного токена."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Мокаем ответ на запрос токена
        responses.add(
            responses.GET,
            "https://test.syrve.online/resto/api/auth",
            body=self.token_response,
            status=200,
            match=[responses.matchers.query_param_matcher({"login": "test_user", "pass": self.client.password_sha1})]
        )
        
        # Получаем токен
        token = self.client.get_token()
        
        # Проверяем результат
        self.assertEqual(token, self.token_response)
        self.assertEqual(len(responses.calls), 1)
        self.assertIn("/resto/api/auth?login=test_user&pass=", responses.calls[0].request.url)

    @responses.activate
    def test_token_error(self):
        """Тестирует ошибку при запросе токена."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Мокаем ошибку при запросе токена
        responses.add(
            responses.GET,
            "https://test.syrve.online/resto/api/auth",
            body="Invalid credentials",
            status=401,
            match=[responses.matchers.query_param_matcher({"login": "test_user", "pass": self.client.password_sha1})]
        )
        
        # Проверяем, что возникает правильное исключение
        with self.assertRaises(InvoiceAuthError):
            self.client.get_token()

    @responses.activate
    def test_successful_invoice_send(self):
        """Тестирует успешную отправку инвойса."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Переопределяем метод get_token, чтобы не делать запрос
        with patch.object(self.client, 'get_token', return_value=self.token_response):
            # Мокаем ответ на отправку инвойса
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body=self.success_response,
                status=200,
                content_type="application/xml",
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            # Отправляем инвойс
            result = self.client.send_invoice(self.valid_invoice)
            
            # Проверяем результат
            self.assertTrue(result.get("valid"))
            self.assertEqual(result.get("document_number"), "SYRVE-20250101-001")

    @responses.activate
    def test_validation_error(self):
        """Тестирует ошибку валидации при отправке инвойса."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Переопределяем метод get_token, чтобы не делать запрос
        with patch.object(self.client, 'get_token', return_value=self.token_response):
            # Мокаем ответ на отправку инвойса с ошибкой валидации
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body=self.invalid_response,
                status=200,
                content_type="application/xml",
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            # Проверяем, что возникает правильное исключение
            with self.assertRaises(InvoiceValidationError) as context:
                self.client.send_invoice(self.invalid_invoice)
            
            # Проверяем сообщение об ошибке
            self.assertIn("Unknown product id", str(context.exception))
            self.assertIn(self.unknown_product_id, str(context.exception))

    @responses.activate
    def test_http_error(self):
        """Тестирует ошибку HTTP при отправке инвойса."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Переопределяем метод get_token, чтобы не делать запрос
        with patch.object(self.client, 'get_token', return_value=self.token_response):
            # Мокаем ответ с HTTP-ошибкой при отправке инвойса
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body="Internal Server Error",
                status=500,
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            # Проверяем, что возникает правильное исключение
            with self.assertRaises(InvoiceHTTPError) as context:
                self.client.send_invoice(self.valid_invoice)
            
            # Проверяем сообщение об ошибке
            self.assertIn("HTTP error 500", str(context.exception))

    @responses.activate
    def test_retries_on_server_error(self):
        """Тестирует повторные попытки при серверных ошибках."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Переопределяем метод get_token, чтобы не делать запрос
        with patch.object(self.client, 'get_token', return_value=self.token_response):
            # Мокаем две ошибки сервера и затем успешный ответ
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body="Service Unavailable",
                status=503,
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body="Service Unavailable",
                status=503,
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body=self.success_response,
                status=200,
                content_type="application/xml",
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            # Отключаем таймеры
            with patch('time.sleep', return_value=None):
                # Отправляем инвойс (должны быть повторные попытки)
                result = self.client.send_invoice(self.valid_invoice)
                
                # Проверяем результат
                self.assertTrue(result.get("valid"))
                self.assertEqual(result.get("document_number"), "SYRVE-20250101-001")

    def test_validation_local(self):
        """Тестирует локальную валидацию данных инвойса."""
        # Тест на некорректный формат GUID
        invalid_guid_invoice = Invoice(
            items=[
                InvoiceItem(
                    num=1,
                    product_id="invalid-guid",
                    amount=Decimal("10.5"),
                    price=Decimal("100.00"),
                    sum=Decimal("1050.00")
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id
        )
        
        with self.assertRaises(InvoiceValidationError) as context:
            self.client.validate_invoice(invalid_guid_invoice)
        self.assertIn("Invalid product_id format", str(context.exception))
        
        # Тест на несоответствие суммы
        invalid_sum_invoice = Invoice(
            items=[
                InvoiceItem(
                    num=1,
                    product_id=self.product_id,
                    amount=Decimal("10.5"),
                    price=Decimal("100.00"),
                    sum=Decimal("999.00")  # Неверная сумма
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id
        )
        
        with self.assertRaises(InvoiceValidationError) as context:
            self.client.validate_invoice(invalid_sum_invoice)
        self.assertIn("does not match price*amount", str(context.exception))
        
        # Тест на отрицательное количество
        invalid_amount_invoice = Invoice(
            items=[
                InvoiceItem(
                    num=1,
                    product_id=self.product_id,
                    amount=Decimal("-1.0"),  # Отрицательное количество
                    price=Decimal("100.00"),
                    sum=Decimal("-100.00")
                )
            ],
            supplier_id=self.supplier_id,
            default_store_id=self.store_id
        )
        
        with self.assertRaises(InvoiceValidationError) as context:
            self.client.validate_invoice(invalid_amount_invoice)
        self.assertIn("amount must be positive", str(context.exception))

    @responses.activate
    def test_server_assigned_document_number(self):
        """Тестирует получение номера документа от сервера."""
        # Создаем HTTP-клиент для теста
        self.client.http = httpx.Client()
        
        # Переопределяем метод get_token, чтобы не делать запрос
        with patch.object(self.client, 'get_token', return_value=self.token_response):
            # Мокаем ответ на отправку инвойса
            responses.add(
                responses.POST,
                "https://test.syrve.online/resto/api/documents/import/incomingInvoice",
                body=self.success_response,
                status=200,
                content_type="application/xml",
                match=[responses.matchers.query_param_matcher({"key": self.token_response})]
            )
            
            # Создаем инвойс без номера документа
            invoice = Invoice(
                items=[
                    InvoiceItem(
                        num=1,
                        product_id=self.product_id,
                        amount=Decimal("10.5"),
                        price=Decimal("100.00"),
                        sum=Decimal("1050.00")
                    )
                ],
                supplier_id=self.supplier_id,
                default_store_id=self.store_id,
                date_incoming=date(2025, 1, 1)
            )
            
            # Отправляем инвойс
            result = self.client.send_invoice(invoice)
            
            # Проверяем результат
            self.assertTrue(result.get("valid"))
            self.assertEqual(result.get("document_number"), "SYRVE-20250101-001")


if __name__ == "__main__":
    unittest.main() 