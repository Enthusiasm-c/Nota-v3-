"""
Модуль для маппинга локальных UUID продуктов на Syrve GUID.
"""
import csv
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Путь к файлу маппинга
MAPPING_FILE = Path("data/syrve_mapping.csv")


class SyrveProductMapper:
    """Класс для управления маппингом продуктов на Syrve GUID."""
    
    def __init__(self):
        self.mapping: Dict[str, str] = {}
        self.name_to_syrve: Dict[str, str] = {}
        self.loaded = False
        
    def load_mapping(self) -> None:
        """Загружает маппинг из CSV файла."""
        if not MAPPING_FILE.exists():
            logger.warning(f"Mapping file {MAPPING_FILE} not found, creating empty")
            MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['local_id', 'syrve_guid'])
            return
            
        try:
            with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    local_id = row.get('local_id', '').strip()
                    syrve_guid = row.get('syrve_guid', '').strip()
                    if local_id and syrve_guid:
                        self.mapping[local_id] = syrve_guid
            
            logger.info(f"Loaded {len(self.mapping)} product mappings from {MAPPING_FILE}")
            self.loaded = True
            
        except Exception as e:
            logger.error(f"Error loading mapping file: {e}")
    
    def get_syrve_guid(self, local_id: str) -> Optional[str]:
        """
        Получает Syrve GUID по локальному ID.
        
        Args:
            local_id: Локальный UUID продукта
            
        Returns:
            Syrve GUID или None
        """
        if not self.loaded:
            self.load_mapping()
        
        return self.mapping.get(local_id)
    
    def add_mapping(self, local_id: str, syrve_guid: str) -> None:
        """
        Добавляет новый маппинг и сохраняет в файл.
        
        Args:
            local_id: Локальный UUID
            syrve_guid: Syrve GUID
        """
        self.mapping[local_id] = syrve_guid
        
        # Добавляем в CSV файл
        try:
            with open(MAPPING_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([local_id, syrve_guid])
            logger.info(f"Added mapping: {local_id} -> {syrve_guid}")
        except Exception as e:
            logger.error(f"Error saving mapping: {e}")
    
    async def fetch_syrve_products(self) -> Dict[str, str]:
        """
        Загружает список продуктов из Syrve API.
        
        Returns:
            Словарь {name: guid}
        """
        try:
            # Получаем токен авторизации
            from app.syrve_client import get_syrve_token
            
            token = await get_syrve_token(
                settings.SYRVE_SERVER_URL,
                settings.SYRVE_LOGIN,
                settings.SYRVE_PASSWORD
            )
            
            if not token:
                logger.error("Failed to get Syrve auth token")
                return {}
            
            # Запрашиваем продукты
            url = f"{settings.SYRVE_SERVER_URL}/resto/api/products?key={token}"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch products: {response.status_code}")
                    return {}
                
                data = response.json()
                
                # Создаем словарь name -> guid
                products = {}
                for item in data:
                    if isinstance(item, dict):
                        guid = item.get('id', '')
                        name = item.get('name', '').lower().strip()
                        if guid and name:
                            products[name] = guid
                            # Также сохраняем альтернативные написания
                            if 'article' in item and item['article']:
                                products[item['article'].lower().strip()] = guid
                
                logger.info(f"Fetched {len(products)} products from Syrve API")
                self.name_to_syrve = products
                return products
                
        except Exception as e:
            logger.error(f"Error fetching Syrve products: {e}")
            return {}
    
    async def update_missing_mappings(self, products: List[Dict[str, any]]) -> None:
        """
        Обновляет маппинг для продуктов без Syrve GUID.
        
        Args:
            products: Список продуктов из локальной базы
        """
        if not self.loaded:
            self.load_mapping()
        
        # Находим продукты без маппинга
        missing = []
        for product in products:
            local_id = product.get('id', '')
            if local_id and local_id not in self.mapping:
                missing.append(product)
        
        if not missing:
            logger.info("All products have Syrve mappings")
            return
        
        logger.info(f"Found {len(missing)} products without Syrve mapping")
        
        # Загружаем каталог Syrve если еще не загружен
        if not self.name_to_syrve:
            await self.fetch_syrve_products()
        
        if not self.name_to_syrve:
            logger.error("Failed to fetch Syrve products catalog")
            return
        
        # Пытаемся найти соответствия по имени
        mapped_count = 0
        for product in missing:
            local_id = product.get('id', '')
            name = product.get('name', '').lower().strip()
            
            if name in self.name_to_syrve:
                syrve_guid = self.name_to_syrve[name]
                self.add_mapping(local_id, syrve_guid)
                mapped_count += 1
                logger.info(f"Auto-mapped '{name}' -> {syrve_guid}")
        
        logger.info(f"Auto-mapped {mapped_count} products to Syrve GUIDs")


# Глобальный экземпляр маппера
_mapper = SyrveProductMapper()


def get_syrve_guid(local_id: str) -> Optional[str]:
    """
    Получает Syrve GUID по локальному ID.
    
    Args:
        local_id: Локальный UUID продукта
        
    Returns:
        Syrve GUID или None
    """
    return _mapper.get_syrve_guid(local_id)


async def ensure_syrve_mappings(products: List[Dict[str, any]]) -> None:
    """
    Обеспечивает наличие Syrve маппингов для всех продуктов.
    
    Args:
        products: Список продуктов из локальной базы
    """
    await _mapper.update_missing_mappings(products)