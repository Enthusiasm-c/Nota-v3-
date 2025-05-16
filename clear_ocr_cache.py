#!/usr/bin/env python3
# Скрипт для очистки кеша OCR

import sys
import logging
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Основная функция очистки кеша
def main():
    try:
        # Импорт функций очистки кеша
        from app.utils.ocr_cache import clear_cache as clear_ocr_cache, get_cache_stats
        from app.utils.cached_loader import clear_cache as clear_data_cache
        
        # Также импортируем функции Redis кеша
        from app.utils.redis_cache import get_redis, cache_get, cache_set
        
        # Статистика кеша OCR до очистки
        stats_before = get_cache_stats()
        logger.info(f"OCR Cache stats before clearing: {stats_before}")
        
        # Очистка кеша OCR
        clear_ocr_cache()
        logger.info("Standard OCR cache cleared")
        
        # Очистка Redis кеша для OCR изображений
        redis_client = get_redis()
        if redis_client:
            try:
                # Получаем все ключи, относящиеся к OCR кешу
                ocr_keys = redis_client.keys("ocr:image:*")
                if ocr_keys:
                    # Удаляем все ключи OCR кеша
                    redis_client.delete(*ocr_keys)
                    logger.info(f"Cleared {len(ocr_keys)} OCR keys from Redis")
                else:
                    logger.info("No OCR keys found in Redis")
            except Exception as e:
                logger.error(f"Error clearing Redis cache: {e}")
        else:
            logger.warning("Redis not available")
        
        # Очистка временных файлов в директории tmp
        try:
            tmp_dir = os.path.join(os.getcwd(), "tmp")
            if os.path.exists(tmp_dir):
                for filename in os.listdir(tmp_dir):
                    if filename.startswith("ocr_cache") or filename.endswith(".jpg") or filename.endswith(".png"):
                        file_path = os.path.join(tmp_dir, filename)
                        try:
                            if os.path.isfile(file_path):
                                os.unlink(file_path)
                                logger.info(f"Deleted temp file: {filename}")
                        except Exception as e:
                            logger.error(f"Error deleting file {filename}: {e}")
        except Exception as e:
            logger.error(f"Error clearing temp files: {e}")
        
        # Очистка кеша данных
        clear_data_cache()
        logger.info("Data cache cleared")
        
        # Проверка статистики после очистки
        stats_after = get_cache_stats()
        logger.info(f"OCR Cache stats after clearing: {stats_after}")
        
        logger.info("All caches cleared successfully!")
        return 0
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 