"""
Модуль для отправки приходных накладных в Syrve API.

Обеспечивает надёжную отправку инвойсов в систему Syrve (iiko Server) через REST API
с поддержкой аутентификации, валидации и обработки ошибок.
"""

import logging
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List, Optional
from xml.dom import minidom

import httpx

# Настройка логгера
logger = logging.getLogger(__name__)

# Константы
GUID_REGEX = re.compile(r"^[0-9a-fA-F-]{36}$")
TOKEN_CACHE_MINUTES = 25  # Время жизни токена в минутах
TOKEN_REFRESH_THRESHOLD = 5  # За сколько минут до истечения обновлять токен


# Исключения
class InvoiceError(Exception):
    """Базовое исключение для ошибок отправки инвойсов."""

    pass


class InvoiceValidationError(InvoiceError):
    """Ошибка валидации инвойса на стороне Syrve API."""

    pass


class InvoiceHTTPError(InvoiceError):
    """Ошибка HTTP при взаимодействии с Syrve API."""

    pass


class InvoiceAuthError(InvoiceError):
    """Ошибка аутентификации при отправке инвойса."""

    pass


@dataclass
class InvoiceItem:
    """
    Элемент приходной накладной.

    Attributes:
        num: Номер строки в накладной
        product_id: GUID товара в системе Syrve
        amount: Количество товара
        price: Цена за единицу
        sum: Общая сумма (amount * price)
        store_id: GUID склада назначения (опционально)
    """

    num: int
    product_id: str  # GUID товара
    amount: Decimal
    price: Decimal
    sum: Decimal
    store_id: Optional[str] = None  # GUID склада (optional)


@dataclass
class Invoice:
    """
    Приходная накладная для импорта в Syrve.

    Attributes:
        items: Список элементов накладной
        supplier_id: GUID поставщика
        default_store_id: GUID склада по умолчанию
        conception_id: GUID концепции (опционально)
        document_number: Номер документа (опционально)
        date_incoming: Дата документа (опционально)
        external_id: Внешний идентификатор (опционально)
    """

    items: List[InvoiceItem]
    supplier_id: str  # GUID поставщика
    default_store_id: str  # GUID склада
    conception_id: Optional[str] = None
    document_number: Optional[str] = None
    date_incoming: Optional[date] = None
    external_id: Optional[str] = None


class SyrveClient:
    """
    Клиент для взаимодействия с Syrve API.

    Позволяет отправлять приходные накладные в Syrve с поддержкой
    аутентификации, валидации и обработки ошибок.
    """

    def __init__(
        self,
        base_url: str,
        login: str,
        password_sha1: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 25.0,
        max_retries: int = 3,
        on_result: Optional[Callable[[bool, float, Optional[Exception]], None]] = None,
    ):
        """
        Инициализирует клиент Syrve API.

        Args:
            base_url: Базовый URL Syrve API
            login: Логин для аутентификации
            password_sha1: SHA1-хеш пароля
            connect_timeout: Таймаут соединения в секундах
            read_timeout: Таймаут чтения в секундах
            max_retries: Максимальное число повторных попыток для запросов
            on_result: Функция обратного вызова для сбора метрик
        """
        self.base_url = base_url.rstrip("/")
        self.login = login
        self.password_sha1 = password_sha1
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries
        self.on_result = on_result

        # Состояние для кэширования токена
        self._token = None
        self._token_expiry = None

        # Настройка HTTP-клиента
        self.http = httpx.Client(timeout=(connect_timeout, read_timeout))

    @classmethod
    def from_env(cls) -> "SyrveClient":
        """
        Создает клиент из переменных окружения.

        Returns:
            SyrveClient: Экземпляр клиента

        Raises:
            ValueError: Если необходимые переменные окружения отсутствуют
        """
        base_url = os.environ.get("SYRVE_BASE_URL")
        login = os.environ.get("SYRVE_LOGIN")
        password_sha1 = os.environ.get("SYRVE_PASS_SHA1")

        if not (base_url and login and password_sha1):
            raise ValueError(
                "Missing required environment variables: "
                "SYRVE_BASE_URL, SYRVE_LOGIN, SYRVE_PASS_SHA1"
            )

        return cls(base_url, login, password_sha1)

    def _is_token_valid(self) -> bool:
        """Проверяет, действителен ли текущий токен"""
        if not self._token or not self._token_expiry:
            return False

        # Проверяем, не истекает ли токен в ближайшее время
        current_time = datetime.now()
        time_until_expiry = (self._token_expiry - current_time).total_seconds() / 60

        return time_until_expiry > TOKEN_REFRESH_THRESHOLD

    def _request_new_token(self) -> str:
        """Запрашивает новый токен у API"""
        auth_url = f"{self.base_url}/resto/api/auth?login={self.login}&pass={self.password_sha1}"

        try:
            response = self.http.get(auth_url)
            response.raise_for_status()

            token = response.text.strip()
            if not token:
                raise InvoiceAuthError("Empty token received from Syrve API")

            # Устанавливаем время жизни токена
            self._token = token
            self._token_expiry = datetime.now() + timedelta(minutes=TOKEN_CACHE_MINUTES)

            logger.info(
                f"Successfully obtained new Syrve token, valid for {TOKEN_CACHE_MINUTES} minutes"
            )
            return token

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error during token request: {e.response.status_code} - {e.response.text}"
            )
            raise InvoiceAuthError(f"HTTP error during authentication: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Network error during token request: {str(e)}")
            raise InvoiceAuthError(f"Network error during authentication: {str(e)}")

    def get_token(self) -> str:
        """
        Получает действующий токен аутентификации, при необходимости запрашивает новый.

        Returns:
            str: Действующий токен доступа

        Raises:
            InvoiceAuthError: При ошибке аутентификации
        """
        # Проверяем локальный токен
        if self._is_token_valid():
            logger.debug(
                "Using cached token (expires in %s minutes)",
                (self._token_expiry - datetime.now()).total_seconds() / 60,
            )
            return self._token

        # Если нет валидного токена, запрашиваем новый
        return self._request_new_token()

    def validate_invoice(self, invoice: Invoice) -> None:
        """
        Выполняет локальную валидацию инвойса перед отправкой.

        Args:
            invoice: Инвойс для валидации

        Raises:
            InvoiceValidationError: При ошибке валидации
        """
        # Валидация GUIDs
        if not GUID_REGEX.match(invoice.supplier_id):
            raise InvoiceValidationError(f"Invalid supplier_id format: {invoice.supplier_id}")

        if not GUID_REGEX.match(invoice.default_store_id):
            raise InvoiceValidationError(
                f"Invalid default_store_id format: {invoice.default_store_id}"
            )

        if invoice.conception_id and not GUID_REGEX.match(invoice.conception_id):
            raise InvoiceValidationError(f"Invalid conception_id format: {invoice.conception_id}")

        if not invoice.items:
            raise InvoiceValidationError("Invoice must contain at least one item")

        # Валидация даты
        today = date.today()
        max_date = today + timedelta(days=1)
        if invoice.date_incoming and invoice.date_incoming > max_date:
            raise InvoiceValidationError(
                f"date_incoming ({invoice.date_incoming}) cannot be later than {max_date}"
            )

        # Проверка каждого элемента
        for item in invoice.items:
            # Проверка GUID
            if not GUID_REGEX.match(item.product_id):
                raise InvoiceValidationError(f"Invalid product_id format: {item.product_id}")

            if item.store_id and not GUID_REGEX.match(item.store_id):
                raise InvoiceValidationError(f"Invalid store_id format: {item.store_id}")

            # Проверка числовых значений
            if item.amount <= 0:
                raise InvoiceValidationError(f"Item {item.num}: amount must be positive")

            if item.price < 0:
                raise InvoiceValidationError(f"Item {item.num}: price cannot be negative")

            if item.sum < 0:
                raise InvoiceValidationError(f"Item {item.num}: sum cannot be negative")

            # Проверка вычислений с округлением
            expected_sum = (item.amount * item.price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            diff = abs(expected_sum - item.sum)

            if diff > Decimal("0.01"):
                raise InvoiceValidationError(
                    f"Item {item.num}: sum ({item.sum}) does not match price*amount "
                    f"({item.price}*{item.amount}={expected_sum}), diff={diff}"
                )

    def generate_invoice_xml(self, invoice: Invoice) -> str:
        """
        Генерирует XML-представление инвойса для отправки в Syrve API.

        Args:
            invoice: Инвойс для преобразования в XML

        Returns:
            str: XML-строка для отправки в API
        """
        # Создаем корневой элемент
        root = ET.Element("document")

        # Добавляем элементы в указанном порядке

        # 1. Items (обязательно)
        items_elem = ET.SubElement(root, "items")
        for item in invoice.items:
            item_elem = ET.SubElement(items_elem, "item")
            ET.SubElement(item_elem, "productId").text = item.product_id
            ET.SubElement(item_elem, "amount").text = str(item.amount)
            ET.SubElement(item_elem, "price").text = str(item.price)
            ET.SubElement(item_elem, "sum").text = str(item.sum)
            if item.store_id:
                ET.SubElement(item_elem, "storeId").text = item.store_id

        # 2. Supplier (обязательно)
        ET.SubElement(root, "supplier").text = invoice.supplier_id

        # 3. DefaultStore (обязательно)
        ET.SubElement(root, "defaultStore").text = invoice.default_store_id

        # 4. Conception (опционально)
        if invoice.conception_id:
            ET.SubElement(root, "conception").text = invoice.conception_id

        # 5. DocumentNumber (опционально)
        if invoice.document_number:
            ET.SubElement(root, "documentNumber").text = invoice.document_number

        # 6. DateIncoming (опционально)
        if invoice.date_incoming:
            ET.SubElement(root, "dateIncoming").text = invoice.date_incoming.strftime("%Y-%m-%d")

        # 7. ExternalId (опционально)
        external_id = invoice.external_id or str(uuid.uuid4())
        if not invoice.external_id:
            logger.info("Using auto-generated external_id: %s", external_id)
        ET.SubElement(root, "externalId").text = external_id

        # Преобразуем в строку с форматированием
        xml_string = ET.tostring(root, encoding="utf-8", method="xml")
        pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")

        return pretty_xml

    def validate_xml_schema(self, xml_string: str) -> None:
        """
        Проверяет XML на соответствие XSD-схеме incomingInvoice.

        Args:
            xml_string: XML-строка для проверки

        Raises:
            InvoiceValidationError: При ошибке валидации по схеме
        """
        # TODO: Реализовать валидацию по XSD
        # В полной реализации здесь должна быть загрузка XSD-схемы и проверка
        # через lxml.etree.XMLSchema
        pass

    def send_invoice_xml(self, xml_string: str) -> bool:
        """
        Отправляет XML-документ в Syrve API.

        Args:
            xml_string: XML-строка для отправки

        Returns:
            bool: True в случае успешной отправки

        Raises:
            InvoiceValidationError: При ошибке валидации инвойса на стороне API
            InvoiceHTTPError: При ошибке HTTP-запроса
        """
        # Получаем токен
        token = self.get_token()

        # Формируем URL
        import_url = f"{self.base_url}/resto/api/documents/import/incomingInvoice?key={token}"

        # Подготовка заголовков
        headers = {"Content-Type": "application/xml", "Accept": "application/xml"}

        # Реализация стратегии повторных попыток
        retries = 0
        last_error = None
        while retries <= self.max_retries:
            try:
                start_time = time.time()
                response = self.http.post(import_url, content=xml_string, headers=headers)
                elapsed_time = time.time() - start_time

                # Обрабатываем ответ
                if response.status_code == 200:
                    # Парсим XML ответа
                    response_root = ET.fromstring(response.text)
                    is_valid = response_root.find("valid")

                    # Проверяем успешность валидации
                    if is_valid is not None and is_valid.text.lower() == "true":
                        logger.info(
                            "Invoice successfully imported to Syrve (%.2f seconds)", elapsed_time
                        )
                        if self.on_result:
                            self.on_result(True, elapsed_time, None)
                        return True
                    else:
                        # Извлекаем сообщение об ошибке
                        error_msg = "Unknown validation error"
                        error_elem = response_root.find("errorMessage")
                        if error_elem is not None and error_elem.text:
                            error_msg = error_elem.text

                        logger.warning("Syrve API validation error: %s", error_msg)
                        if self.on_result:
                            error = InvoiceValidationError(error_msg)
                            self.on_result(False, elapsed_time, error)
                        raise InvoiceValidationError(error_msg)

                # Обрабатываем HTTP-ошибки
                response.raise_for_status()

            except httpx.HTTPStatusError as e:
                # HTTP-ошибка со статус-кодом
                status_code = e.response.status_code
                elapsed_time = time.time() - start_time

                # Проверяем, можно ли повторить запрос
                if status_code in (502, 503, 504) and retries < self.max_retries:
                    retries += 1
                    sleep_time = 2**retries  # Экспоненциальная задержка: 1, 2, 4 секунды
                    logger.warning(
                        "Syrve API HTTP %d error, retry %d/%d after %d seconds",
                        status_code,
                        retries,
                        self.max_retries,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    last_error = e
                    continue

                # Логируем ошибку
                logger.error("Syrve API HTTP %d error: %s", status_code, e.response.text)

                # Извлекаем request_id если есть
                request_id = e.response.headers.get("X-Request-Id", "unknown")
                error_msg = f"HTTP error {status_code}, Request-ID: {request_id}"

                if self.on_result:
                    error = InvoiceHTTPError(error_msg)
                    self.on_result(False, elapsed_time, error)

                raise InvoiceHTTPError(error_msg)

            except httpx.RequestError as e:
                # Ошибка сети/таймаут
                elapsed_time = time.time() - start_time

                if retries < self.max_retries:
                    retries += 1
                    sleep_time = 2**retries
                    logger.warning(
                        "Syrve API network error, retry %d/%d after %d seconds: %s",
                        retries,
                        self.max_retries,
                        sleep_time,
                        str(e),
                    )
                    time.sleep(sleep_time)
                    last_error = e
                    continue

                logger.error("Syrve API network error: %s", str(e))

                if self.on_result:
                    error = InvoiceHTTPError(f"Network error: {str(e)}")
                    self.on_result(False, elapsed_time, error)

                raise InvoiceHTTPError(f"Network error: {str(e)}")

        # Если мы здесь, значит все попытки завершились неудачно
        if last_error:
            raise last_error

        # Этот код не должен выполняться, просто для предотвращения ошибок линтера
        return False

    def send_invoice(self, invoice: Invoice) -> bool:
        """
        Отправляет инвойс в Syrve API.

        Args:
            invoice: Инвойс для отправки

        Returns:
            bool: True в случае успешной отправки

        Raises:
            InvoiceValidationError: При ошибке валидации
            InvoiceHTTPError: При ошибке HTTP-запроса
            InvoiceAuthError: При ошибке аутентификации
        """
        # Добавляем номер документа, если не указан
        if not invoice.document_number:
            # Генерируем номер документа
            today_str = date.today().strftime("%Y%m%d")
            invoice.document_number = f"AUTO-{today_str}-{uuid.uuid4().hex[:8].upper()}"
            logger.info("Using auto-generated document_number: %s", invoice.document_number)

        # Устанавливаем дату, если не указана
        if not invoice.date_incoming:
            invoice.date_incoming = date.today()

        # Валидируем инвойс
        self.validate_invoice(invoice)

        # Генерируем XML
        xml_string = self.generate_invoice_xml(invoice)

        # Валидируем по схеме
        self.validate_xml_schema(xml_string)

        # Отправляем в Syrve
        return self.send_invoice_xml(xml_string)
