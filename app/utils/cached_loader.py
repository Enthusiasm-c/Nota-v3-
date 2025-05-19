"""
Оптимизированный кеш для данных и результатов сравнения строк.

Модуль предоставляет функции для:
1. Эффективной загрузки данных из файлов с кешированием по времени и mtime
2. Кеширования результатов сравнения строк для ускорения работы matcher
3. Статистики использования кеша
"""

import time
import os
import threading
import logging
import functools
import asyncio
from typing import Dict, Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# Глобальный кеш для данных продуктов и поставщиков с отслеживанием времени модификации файлов
_DATA_CACHE = {}
_MODIFIED_TIMES = {}
_CACHE_LOCK = threading.RLock()

# Кеш для результатов сравнения строк с оптимизированной очисткой
_STRING_CACHE = {}
_STRING_CACHE_LOCK = threading.RLock()
_STRING_CACHE_MAX_SIZE = 25000  # Увеличенный размер кеша
_STRING_CACHE_HITS = 0
_STRING_CACHE_MISSES = 0

# Интервал проверки изменения файлов (в секундах)
CHECK_INTERVAL = 60  # 1 минута

# Флаг того, запущен ли фоновый поток очистки кеша
_CLEANUP_THREAD_RUNNING = False
_CLEANUP_THREAD_STOP = threading.Event()

def _start_cleanup_thread():
    """Запускает фоновый поток для периодической очистки и мониторинга кеша."""
    global _CLEANUP_THREAD_RUNNING, _CLEANUP_THREAD_STOP
    
    if _CLEANUP_THREAD_RUNNING:
        return
        
    _CLEANUP_THREAD_STOP.clear()
    
    def cleanup_worker():
        global _CLEANUP_THREAD_RUNNING
        _CLEANUP_THREAD_RUNNING = True
        
        logger.info("Запущен поток очистки кеша данных")
        
        try:
            while not _CLEANUP_THREAD_STOP.is_set():
                # Проверяем размер строкового кеша и очищаем при необходимости
                with _STRING_CACHE_LOCK:
                    if len(_STRING_CACHE) > _STRING_CACHE_MAX_SIZE * 0.9:
                        # Удаляем 30% записей для избежания частых очисток
                        items_to_remove = int(_STRING_CACHE_MAX_SIZE * 0.3)
                        keys_to_remove = list(_STRING_CACHE.keys())[:items_to_remove]
                        for k in keys_to_remove:
                            _STRING_CACHE.pop(k, None)
                        
                        logger.info(f"Очищено {items_to_remove} записей из строкового кеша")
                        
                    # Логируем статистику использования кеша
                    if _STRING_CACHE_HITS + _STRING_CACHE_MISSES > 10000:
                        hit_rate = _STRING_CACHE_HITS / (_STRING_CACHE_HITS + _STRING_CACHE_MISSES) * 100
                        logger.info(f"Статистика кеша строк: {_STRING_CACHE_HITS} попаданий, "
                                  f"{_STRING_CACHE_MISSES} промахов, {hit_rate:.1f}% эффективность")
                
                # Ждем некоторое время перед следующей проверкой
                # Используем мелкие интервалы для быстрого реагирования на остановку
                for _ in range(60):  # 60 * 1 = 60 секунд
                    if _CLEANUP_THREAD_STOP.is_set():
                        break
                    _CLEANUP_THREAD_STOP.wait(1)  # 1 секунда
                    
        except Exception as e:
            logger.error(f"Ошибка в потоке очистки кеша: {e}")
        finally:
            _CLEANUP_THREAD_RUNNING = False
            logger.info("Поток очистки кеша остановлен")
    
    # Запускаем поток
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    
    # Регистрируем функцию остановки при выходе
    import atexit
    
    def stop_cleanup_thread():
        if _CLEANUP_THREAD_RUNNING:
            logger.info("Останавливаем поток очистки кеша...")
            _CLEANUP_THREAD_STOP.set()
            
    atexit.register(stop_cleanup_thread)

def cached_load_data(path: str, loader_func: Callable, cache_key: str = None) -> List[Dict[str, Any]]:
    """
    Загружает данные из файла с кешированием результатов.
    Отслеживает изменения файла по времени модификации.
    
    Args:
        path: Путь к файлу с данными
        loader_func: Функция загрузки, которая принимает путь к файлу
        cache_key: Дополнительный ключ для кеширования (если нужны разные версии)
        
    Returns:
        Загруженные данные (из кеша или напрямую)
    """
    full_key = f"{cache_key or 'data'}:{path}"
    
    # Проверяем наличие файла
    if not os.path.exists(path):
        logger.warning(f"Файл {path} не найден")
        # Возвращаем кешированные данные, если они есть
        with _CACHE_LOCK:
            if full_key in _DATA_CACHE:
                logger.warning(f"Используем кешированные данные для недоступного файла {path}")
                return _DATA_CACHE[full_key]
        return []
    
    with _CACHE_LOCK:
        # Проверяем время модификации файла
        current_mtime = os.path.getmtime(path)
        last_check_time = time.time()
        
        # Если данные уже в кеше и файл не изменился, используем кеш
        if (full_key in _DATA_CACHE and 
            full_key in _MODIFIED_TIMES and 
            current_mtime <= _MODIFIED_TIMES[full_key]["mtime"] and
            last_check_time - _MODIFIED_TIMES[full_key]["checked"] < CHECK_INTERVAL):
            logger.debug(f"Используем кешированные данные для {path} ({len(_DATA_CACHE[full_key])} записей)")
            return _DATA_CACHE[full_key]
        
        # Если файл изменился или данных нет в кеше, загружаем
        start_time = time.time()
        try:
            logger.info(f"Загрузка данных из {path}...")
            data = loader_func(path)
            
            # Обновляем кеш
            _DATA_CACHE[full_key] = data
            _MODIFIED_TIMES[full_key] = {
                "mtime": current_mtime,
                "checked": last_check_time
            }
            
            load_time = time.time() - start_time
            logger.info(f"Загружено {len(data)} записей из {path} за {load_time:.2f}с")
            return data
        except Exception as e:
            logger.error(f"Ошибка при загрузке {path}: {e}")
            
            # Используем кешированные данные в случае ошибки, если они есть
            if full_key in _DATA_CACHE:
                logger.warning(f"Используем устаревшие кешированные данные для {path}")
                return _DATA_CACHE[full_key]
            
            return []

async def cached_load_data_async(path: str, loader_func: Callable, cache_key: str = None) -> List[Dict[str, Any]]:
    """
    Асинхронная версия загрузки данных из файла с кешированием.
    
    Args:
        path: Путь к файлу с данными
        loader_func: Функция загрузки (может быть асинхронной)
        cache_key: Дополнительный ключ для кеширования
        
    Returns:
        Загруженные данные
    """
    full_key = f"{cache_key or 'data'}:{path}"
    
    # Проверяем наличие файла без блокировки
    if not os.path.exists(path):
        logger.warning(f"Файл {path} не найден (async)")
        # Возвращаем кешированные данные, если они есть
        with _CACHE_LOCK:
            if full_key in _DATA_CACHE:
                logger.warning(f"Используем кешированные данные для недоступного файла {path} (async)")
                return _DATA_CACHE[full_key]
        return []
    
    # Проверяем кеш
    with _CACHE_LOCK:
        # Проверяем время модификации файла
        current_mtime = os.path.getmtime(path)
        last_check_time = time.time()
        
        # Если данные уже в кеше и файл не изменился, используем кеш
        if (full_key in _DATA_CACHE and 
            full_key in _MODIFIED_TIMES and 
            current_mtime <= _MODIFIED_TIMES[full_key]["mtime"] and
            last_check_time - _MODIFIED_TIMES[full_key]["checked"] < CHECK_INTERVAL):
            logger.debug(f"Используем кешированные данные для {path} (async)")
            return _DATA_CACHE[full_key]
    
    # Если файл изменился или данных нет в кеше, загружаем
    start_time = time.time()
    try:
        logger.info(f"Асинхронная загрузка данных из {path}...")
        
        # Проверяем, является ли функция загрузки асинхронной
        if asyncio.iscoroutinefunction(loader_func):
            data = await loader_func(path)
        else:
            # Если функция синхронная, запускаем ее в отдельном потоке
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: loader_func(path))
        
        # Обновляем кеш
        with _CACHE_LOCK:
            _DATA_CACHE[full_key] = data
            _MODIFIED_TIMES[full_key] = {
                "mtime": current_mtime,
                "checked": last_check_time
            }
        
        load_time = time.time() - start_time
        logger.info(f"Асинхронно загружено {len(data)} записей из {path} за {load_time:.2f}с")
        return data
    except Exception as e:
        logger.error(f"Ошибка при асинхронной загрузке {path}: {e}")
        
        # Используем кешированные данные в случае ошибки, если они есть
        with _CACHE_LOCK:
            if full_key in _DATA_CACHE:
                logger.warning(f"Используем устаревшие кешированные данные для {path} (async)")
                return _DATA_CACHE[full_key]
        
        return []

def cached_load_products(csv_path: str, loader_func: Callable) -> List[Dict]:
    """
    Загружает и кеширует продукты из CSV файла.
    Проверяет изменения файла и обновляет кеш при необходимости.
    
    Args:
        csv_path: Путь к файлу CSV
        loader_func: Функция для загрузки данных
        
    Returns:
        Список продуктов
    """
    # Запускаем поток очистки, если он еще не запущен
    if not _CLEANUP_THREAD_RUNNING:
        _start_cleanup_thread()
        
    return cached_load_data(csv_path, loader_func, "products")

def cached_load_suppliers(csv_path: str, loader_func: Callable) -> List[Dict]:
    """
    Загружает и кеширует поставщиков из CSV файла.
    Проверяет изменения файла и обновляет кеш при необходимости.
    
    Args:
        csv_path: Путь к файлу CSV
        loader_func: Функция для загрузки данных
        
    Returns:
        Список поставщиков
    """
    # Запускаем поток очистки, если он еще не запущен
    if not _CLEANUP_THREAD_RUNNING:
        _start_cleanup_thread()
        
    return cached_load_data(csv_path, loader_func, "suppliers")

def cached_compare_strings(func: Callable) -> Callable:
    """
    Улучшенный декоратор для кеширования сравнения строк.
    Добавляет поддержку сортировки строк для устойчивости ключа.
    
    Args:
        func: Функция сравнения строк
        
    Returns:
        Обернутая функция с кешированием
    """
    @functools.wraps(func)
    def wrapper(s1: str, s2: str, *args, **kwargs) -> float:
        global _STRING_CACHE, _STRING_CACHE_HITS, _STRING_CACHE_MISSES
        
        # Сортируем строки для обеспечения того же результата при разном порядке
        strings = tuple(sorted([s1, s2]))
        
        # Создаем ключ, включая дополнительные аргументы
        args_key = tuple(args)
        kwargs_key = tuple(sorted([(k, v) for k, v in kwargs.items()]))
        cache_key = (strings, args_key, kwargs_key)
        
        with _STRING_CACHE_LOCK:
            if cache_key in _STRING_CACHE:
                _STRING_CACHE_HITS += 1
                return _STRING_CACHE[cache_key]
            
            _STRING_CACHE_MISSES += 1
            
            # Получаем результат
            result = func(s1, s2, *args, **kwargs)
            
            # Сохраняем результат
            _STRING_CACHE[cache_key] = result
            
            return result
    
    return wrapper

def clear_cache(cache_type: Optional[str] = None) -> None:
    """
    Очищает кеш данных.
    
    Args:
        cache_type: Тип кеша для очистки ("products", "suppliers", "strings" или None для всех)
    """
    if cache_type in (None, "products", "suppliers", "data"):
        with _CACHE_LOCK:
            if cache_type is None:
                # Очищаем весь кеш данных
                _DATA_CACHE.clear()
                _MODIFIED_TIMES.clear()
                logger.info("Весь кеш данных очищен")
            else:
                # Очищаем конкретный тип кеша
                keys_to_remove = [k for k in _DATA_CACHE if k.startswith(f"{cache_type}:")]
                for k in keys_to_remove:
                    _DATA_CACHE.pop(k, None)
                    _MODIFIED_TIMES.pop(k, None)
                logger.info(f"Кеш {cache_type} очищен")
                
    if cache_type in (None, "strings"):
        with _STRING_CACHE_LOCK:
            _STRING_CACHE.clear()
            _STRING_CACHE_HITS = 0
            _STRING_CACHE_MISSES = 0
            logger.info("Кеш сравнения строк очищен")

def get_cache_stats() -> Dict[str, Any]:
    """
    Возвращает статистику использования всех типов кеша.
    
    Returns:
        Словарь со статистикой кеша
    """
    stats = {}
    
    with _CACHE_LOCK:
        stats["data_cache"] = {
            "size": len(_DATA_CACHE),
            "keys": list(_DATA_CACHE.keys()),
            "entry_sizes": {k: len(_DATA_CACHE[k]) if hasattr(_DATA_CACHE[k], "__len__") else 1 
                           for k in _DATA_CACHE},
            "last_modified": {k: time.ctime(_MODIFIED_TIMES[k]["mtime"]) 
                             for k in _MODIFIED_TIMES}
        }
    
    with _STRING_CACHE_LOCK:
        total_queries = _STRING_CACHE_HITS + _STRING_CACHE_MISSES
        hit_rate = (_STRING_CACHE_HITS / total_queries * 100) if total_queries > 0 else 0
        
        stats["string_cache"] = {
            "size": len(_STRING_CACHE),
            "max_size": _STRING_CACHE_MAX_SIZE,
            "hits": _STRING_CACHE_HITS,
            "misses": _STRING_CACHE_MISSES,
            "hit_rate": hit_rate,
            "memory_usage_approx": len(_STRING_CACHE) * 100  # Примерный размер в байтах
        }
    
    return stats