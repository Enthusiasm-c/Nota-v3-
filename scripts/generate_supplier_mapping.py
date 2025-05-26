#!/usr/bin/env python3
"""
Скрипт для генерации автоматического маппинга поставщиков.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.supplier_mapping import ensure_supplier_mappings
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    """Генерирует маппинг поставщиков."""
    print("🔄 Generating supplier mappings...")
    
    try:
        await ensure_supplier_mappings()
        print("✅ Supplier mappings generated successfully!")
        
    except Exception as e:
        print(f"❌ Error generating supplier mappings: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())