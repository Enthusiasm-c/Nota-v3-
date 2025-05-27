"""
Модуль для маппинга локальных поставщиков на Syrve supplier GUID.
Аналогично product mapping, но для поставщиков.
"""
import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.matcher import calculate_string_similarity

logger = logging.getLogger(__name__)

# Путь к файлу маппинга поставщиков
SUPPLIER_MAPPING_FILE = Path("data/supplier_mapping.csv")


class SupplierMapper:
    """Класс для управления маппингом поставщиков на Syrve GUID."""
    
    def __init__(self):
        self.mapping: Dict[str, str] = {}  # supplier_name -> syrve_guid
        self.loaded = False
        
    def load_mapping(self) -> None:
        """Загружает маппинг из CSV файла."""
        if not SUPPLIER_MAPPING_FILE.exists():
            logger.warning(f"Supplier mapping file {SUPPLIER_MAPPING_FILE} not found, creating empty")
            SUPPLIER_MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SUPPLIER_MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['supplier_name', 'syrve_guid'])
            return
            
        try:
            with open(SUPPLIER_MAPPING_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    supplier_name = row.get('supplier_name', '').strip().lower()
                    syrve_guid = row.get('syrve_guid', '').strip()
                    if supplier_name and syrve_guid:
                        self.mapping[supplier_name] = syrve_guid
            
            logger.info(f"Loaded {len(self.mapping)} supplier mappings from {SUPPLIER_MAPPING_FILE}")
            self.loaded = True
            
        except Exception as e:
            logger.error(f"Error loading supplier mapping file: {e}")
    
    def get_syrve_guid(self, supplier_name: str) -> Optional[str]:
        """
        Получает Syrve GUID по названию поставщика.
        Сначала ищет в собственном маппинге, затем в base_suppliers.csv
        
        Args:
            supplier_name: Название поставщика
            
        Returns:
            Syrve GUID или None
        """
        if not self.loaded:
            self.load_mapping()
        
        if not supplier_name:
            return None
            
        normalized_name = supplier_name.strip().lower()
        
        # 1. Прямое совпадение в собственном маппинге
        if normalized_name in self.mapping:
            return self.mapping[normalized_name]
        
        # 2. Fuzzy поиск в собственном маппинге
        best_match = None
        best_score = 0.0
        
        for mapped_name, guid in self.mapping.items():
            similarity = calculate_string_similarity(normalized_name, mapped_name)
            if similarity > best_score and similarity >= 0.7:
                best_score = similarity
                best_match = guid
        
        if best_match:
            logger.info(f"Fuzzy match in mapping for supplier '{supplier_name}' -> score: {best_score:.3f}")
            return best_match
            
        # 3. Поиск в base_suppliers.csv
        try:
            from app.data_loader import load_suppliers
            base_suppliers = load_suppliers()
            
            for supplier in base_suppliers:
                supplier_base_name = supplier.get('name', '').strip().lower()
                supplier_id = supplier.get('id', '').strip()
                
                if not supplier_base_name or not supplier_id:
                    continue
                    
                # Прямое совпадение в базе
                if normalized_name == supplier_base_name:
                    logger.info(f"Direct match in base_suppliers for '{supplier_name}' -> {supplier_id}")
                    return supplier_id
                    
                # Fuzzy поиск в базе
                similarity = calculate_string_similarity(normalized_name, supplier_base_name)
                if similarity > best_score and similarity >= 0.7:
                    best_score = similarity
                    best_match = supplier_id
            
            if best_match:
                logger.info(f"Fuzzy match in base_suppliers for supplier '{supplier_name}' -> score: {best_score:.3f}")
                
        except Exception as e:
            logger.error(f"Error searching in base_suppliers.csv: {e}")
            
        return best_match
    
    def add_mapping(self, supplier_name: str, syrve_guid: str) -> None:
        """
        Добавляет новый маппинг и сохраняет в файл.
        
        Args:
            supplier_name: Название поставщика
            syrve_guid: Syrve GUID
        """
        normalized_name = supplier_name.strip().lower()
        self.mapping[normalized_name] = syrve_guid
        
        # Добавляем в CSV файл
        try:
            with open(SUPPLIER_MAPPING_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([supplier_name, syrve_guid])
            logger.info(f"Added supplier mapping: {supplier_name} -> {syrve_guid}")
        except Exception as e:
            logger.error(f"Error saving supplier mapping: {e}")

    async def fetch_syrve_suppliers(self) -> Dict[str, str]:
        """
        Загружает список поставщиков из Syrve API.
        
        Returns:
            Словарь {name: guid}
        """
        try:
            from app.services.unified_syrve_client import UnifiedSyrveClient
            
            client = UnifiedSyrveClient(
                base_url=settings.SYRVE_SERVER_URL,
                login=settings.SYRVE_LOGIN,
                password=settings.SYRVE_PASSWORD,
                verify_ssl=settings.VERIFY_SSL
            )
            
            # Получаем токен авторизации
            token = await client.get_token_async()
            if not token:
                logger.error("Failed to get Syrve auth token for suppliers")
                return {}
            
            # Запрашиваем поставщиков
            import httpx
            url = f"{settings.SYRVE_SERVER_URL}/resto/api/suppliers?key={token}"
            
            async with httpx.AsyncClient(verify=settings.VERIFY_SSL, timeout=30) as http_client:
                response = await http_client.get(url)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch suppliers: {response.status_code}")
                    return {}
                
                # Парсим XML ответ
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                
                suppliers = {}
                for supplier in root.findall('.//supplierDto'):
                    supplier_id = supplier.find('id')
                    supplier_name = supplier.find('name')
                    
                    if supplier_id is not None and supplier_name is not None:
                        suppliers[supplier_name.text.lower().strip()] = supplier_id.text
                
                logger.info(f"Fetched {len(suppliers)} suppliers from Syrve API")
                return suppliers
                
        except Exception as e:
            logger.error(f"Error fetching Syrve suppliers: {e}")
            return {}

    async def auto_generate_mapping(self) -> None:
        """
        Автоматически генерирует маппинг поставщиков на основе локальной базы и Syrve API.
        """
        try:
            # Загружаем локальных поставщиков
            from app.data_loader import load_suppliers
            local_suppliers = load_suppliers()
            
            # Загружаем поставщиков из Syrve
            syrve_suppliers = await self.fetch_syrve_suppliers()
            
            if not syrve_suppliers:
                logger.error("No suppliers fetched from Syrve API")
                return
            
            # Создаем маппинг
            mappings = []
            
            for supplier in local_suppliers:
                supplier_name = getattr(supplier, 'name', '') or supplier.get('name', '')
                if not supplier_name:
                    continue
                
                # Ищем лучшее совпадение в Syrve
                best_match = None
                best_score = 0.0
                
                for syrve_name, syrve_guid in syrve_suppliers.items():
                    similarity = calculate_string_similarity(supplier_name.lower(), syrve_name)
                    
                    if similarity > best_score:
                        best_score = similarity
                        best_match = (syrve_name, syrve_guid)
                
                if best_match and best_score >= 0.75:  # Порог для автоматического маппинга
                    mappings.append({
                        'supplier_name': supplier_name,
                        'syrve_name': best_match[0],
                        'syrve_guid': best_match[1],
                        'similarity': best_score
                    })
                    logger.info(f"Auto-mapped: {supplier_name} -> {best_match[0]} (score: {best_score:.3f})")
            
            # Сохраняем маппинг
            if mappings:
                with open(SUPPLIER_MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['supplier_name', 'syrve_guid'])
                    
                    for mapping in mappings:
                        writer.writerow([mapping['supplier_name'], mapping['syrve_guid']])
                
                logger.info(f"Generated {len(mappings)} supplier mappings")
                
                # Перезагружаем маппинг
                self.loaded = False
                self.load_mapping()
            else:
                logger.warning("No supplier mappings generated")
                
        except Exception as e:
            logger.error(f"Error auto-generating supplier mapping: {e}")


# Глобальный экземпляр маппера
_supplier_mapper = SupplierMapper()


def get_supplier_syrve_guid(supplier_name: str) -> Optional[str]:
    """
    Получает Syrve GUID по названию поставщика.
    
    Args:
        supplier_name: Название поставщика
        
    Returns:
        Syrve GUID или None
    """
    return _supplier_mapper.get_syrve_guid(supplier_name)


def get_available_suppliers() -> List[str]:
    """
    Получает список доступных поставщиков для выбора пользователем.
    
    Returns:
        Список названий поставщиков
    """
    if not _supplier_mapper.loaded:
        _supplier_mapper.load_mapping()
    
    return list(_supplier_mapper.mapping.keys())


async def ensure_supplier_mappings() -> None:
    """
    Обеспечивает наличие маппингов поставщиков.
    """
    await _supplier_mapper.auto_generate_mapping()


def resolve_manual_supplier(manual_supplier_name: str) -> Optional[str]:
    """
    Обрабатывает ручной ввод поставщика пользователем.
    
    Args:
        manual_supplier_name: Название поставщика введенное пользователем
        
    Returns:
        Syrve GUID поставщика или None если не найден
    """
    if not manual_supplier_name:
        return None
    
    # Используем тот же механизм fuzzy поиска с порогом 90%
    syrve_guid = get_supplier_syrve_guid(manual_supplier_name)
    
    if syrve_guid:
        logger.info(f"✅ Manual supplier '{manual_supplier_name}' resolved to {syrve_guid}")
        return syrve_guid
    
    logger.warning(f"❌ Manual supplier '{manual_supplier_name}' not found in mappings")
    return None


def resolve_supplier_for_invoice(invoice_data: dict, manual_supplier: Optional[str] = None) -> str:
    """
    Определяет правильный GUID поставщика для накладной.
    НИКОГДА не использует поставщика по умолчанию - требует точного маппинга.
    
    Args:
        invoice_data: Данные накладной (включая supplier из OCR)
        manual_supplier: Поставщик введенный пользователем вручную (опционально)
        
    Returns:
        Syrve GUID поставщика
        
    Raises:
        ValueError: Если поставщик не найден или не может быть определен
    """
    
    # Приоритет ручному вводу пользователя
    if manual_supplier:
        syrve_guid = resolve_manual_supplier(manual_supplier)
        if syrve_guid:
            return syrve_guid
        else:
            # Ручной ввод не найден
            raise ValueError(
                f"❌ Поставщик '{manual_supplier}' не найден в базе данных.\n\n"
                f"💡 Пожалуйста, проверьте правильность написания поставщика."
            )
    
    # Получаем поставщика из накладной OCR
    detected_supplier = invoice_data.get('supplier')
    
    if not detected_supplier:
        raise ValueError(
            "❌ Поставщик не обнаружен в накладной OCR.\n\n"
            "💡 Пожалуйста, введите название поставщика кнопкой 'Указать поставщика'."
        )
    
    # Пытаемся найти маппинг с порогом точности 70% для автоподтягивания
    syrve_guid = get_supplier_syrve_guid(detected_supplier)
    
    if syrve_guid:
        logger.info(f"✅ Resolved supplier '{detected_supplier}' -> {syrve_guid}")
        return syrve_guid
    
    # Поставщик не найден - предлагаем ручной ввод
    raise ValueError(
        f"❌ Поставщик '{detected_supplier}' не найден в базе данных.\n\n"
        f"💡 Пожалуйста, введите корректное название поставщика кнопкой 'Указать поставщика'"
    )