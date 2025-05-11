import os
import pytest
import asyncio
import hashlib
from dotenv import load_dotenv
from app.syrve_client import SyrveClient

# Загрузка переменных из .env файла
load_dotenv()

# Для интеграционного теста используйте реальные переменные окружения или .env
SYRVE_SERVER_URL = os.getenv("SYRVE_SERVER_URL", "http://localhost:8080")
SYRVE_LOGIN = os.getenv("SYRVE_LOGIN", "test") 
SYRVE_PASSWORD = os.getenv("SYRVE_PASSWORD", "test")

# Проверка загрузки переменных
print(f"SYRVE_SERVER_URL={SYRVE_SERVER_URL}")
print(f"SYRVE_LOGIN={SYRVE_LOGIN}")
print(f"SYRVE_PASSWORD={SYRVE_PASSWORD}")

@pytest.mark.asyncio
async def test_auth_and_logout():
    # Отладочная информация
    print(f"DEBUG: SYRVE_SERVER_URL={SYRVE_SERVER_URL}")
    print(f"DEBUG: SYRVE_LOGIN={SYRVE_LOGIN}")
    print(f"DEBUG: SYRVE_PASSWORD={SYRVE_PASSWORD}")
    print(f"DEBUG: SHA1 hash={hashlib.sha1(SYRVE_PASSWORD.encode()).hexdigest()}")
    
    client = SyrveClient(SYRVE_SERVER_URL, SYRVE_LOGIN, SYRVE_PASSWORD)
    token = await client.auth()
    assert isinstance(token, str) and len(token) > 10
    # Проверим повторную авторизацию (должен вернуть тот же токен из кэша)
    token2 = await client.auth()
    assert token == token2
    # Логаут (токен должен сброситься)
    await client.logout(token)

@pytest.mark.asyncio
async def test_suppliers():
    client = SyrveClient(SYRVE_SERVER_URL, SYRVE_LOGIN, SYRVE_PASSWORD)
    token = await client.auth()
    suppliers = await client.get_suppliers(token)
    assert isinstance(suppliers, list)

@pytest.mark.asyncio
async def test_import_invoice():
    client = SyrveClient(SYRVE_SERVER_URL, SYRVE_LOGIN, SYRVE_PASSWORD)
    token = await client.auth()
    # Пример минимального валидного XML (заполните корректными GUID и значениями для вашего стенда)
    xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<document>
  <items>
    <item>
      <amount>1.00</amount>
      <supplierProduct>00000000-0000-0000-0000-000000000000</supplierProduct>
      <product>00000000-0000-0000-0000-000000000000</product>
      <num>1</num>
      <containerId>00000000-0000-0000-0000-000000000000</containerId>
      <amountUnit>00000000-0000-0000-0000-000000000000</amountUnit>
      <actualUnitWeight/>
      <discountSum>0.00</discountSum>
      <sumWithoutNds>10.00</sumWithoutNds>
      <ndsPercent>0.00</ndsPercent>
      <sum>10.00</sum>
      <priceUnit/>
      <price>10.00</price>
      <code>12345</code>
      <store>00000000-0000-0000-0000-000000000000</store>
      <customsDeclarationNumber>cdn-1</customsDeclarationNumber>
      <actualAmount>1.00</actualAmount>
    </item>
  </items>
  <conception>00000000-0000-0000-0000-000000000000</conception>
  <comment>test</comment>
  <documentNumber>dn-1</documentNumber>
  <dateIncoming>2024-01-01</dateIncoming>
  <useDefaultDocumentTime>true</useDefaultDocumentTime>
  <invoice>in-1</invoice>
  <defaultStore>00000000-0000-0000-0000-000000000000</defaultStore>
  <supplier>00000000-0000-0000-0000-000000000000</supplier>
  <dueDate>2024-01-10</dueDate>
  <incomingDocumentNumber>idn-1</incomingDocumentNumber>
  <employeePassToAccount>00000000-0000-0000-0000-000000000000</employeePassToAccount>
  <transportInvoiceNumber>tin-1</transportInvoiceNumber>
</document>'''
    result = await client.import_invoice(token, xml)
    assert isinstance(result, dict)
    assert "valid" in result
    # Логаут в конце
    await client.logout(token)
