import hashlib
import os

import pytest
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
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<document>
  <items>
    <item>
      <amount>1.00</amount>
      <product>00000000-0000-0000-0000-000000000000</product>
      <num>1</num>
      <sum>10.00</sum>
      <price>10.00</price>
      <store>00000000-0000-0000-0000-000000000000</store>
    </item>
  </items>
  <conception>00000000-0000-0000-0000-000000000000</conception>
  <dateIncoming>2024-01-01</dateIncoming>
  <defaultStore>00000000-0000-0000-0000-000000000000</defaultStore>
  <supplier>00000000-0000-0000-0000-000000000000</supplier>
</document>"""
    result = await client.import_invoice(token, xml)
    assert isinstance(result, dict)
    assert "valid" in result
    # Логаут в конце
    await client.logout(token)


@pytest.mark.asyncio
async def test_server_assigned_document_number():
    """Тест проверяет, что сервер может присвоить номер документа."""
    client = SyrveClient(SYRVE_SERVER_URL, SYRVE_LOGIN, SYRVE_PASSWORD)
    token = await client.auth()

    # XML без номера документа
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<document>
  <items>
    <item>
      <amount>1.00</amount>
      <product>00000000-0000-0000-0000-000000000000</product>
      <num>1</num>
      <sum>10.00</sum>
      <price>10.00</price>
      <store>00000000-0000-0000-0000-000000000000</store>
    </item>
  </items>
  <conception>00000000-0000-0000-0000-000000000000</conception>
  <dateIncoming>2024-01-01</dateIncoming>
  <defaultStore>00000000-0000-0000-0000-000000000000</defaultStore>
  <supplier>00000000-0000-0000-0000-000000000000</supplier>
</document>"""

    result = await client.import_invoice(token, xml)
    assert isinstance(result, dict)
    assert result["valid"] is True
    assert "document_number" in result
    assert result["document_number"] is not None
    # Логаут в конце
    await client.logout(token)
