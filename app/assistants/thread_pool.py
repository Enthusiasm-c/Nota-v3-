"""
Модуль для управления пулом потоков OpenAI.
Обеспечивает предварительное создание thread для ускорения работы с OpenAI Assistant API.
"""

import asyncio
import logging
from typing import List, Optional
import time

logger = logging.getLogger(__name__)

# Глобальный пул предсозданных threads
_threads_pool = []
_pool_lock = asyncio.Lock()
_last_refill = 0
POOL_SIZE = 5
REFILL_INTERVAL = 60  # секунды между пополнениями пула

async def initialize_pool(client, size: int = POOL_SIZE):
    """
    Инициализировать пул потоков при запуске.
    
    Args:
        client: OpenAI API клиент
        size: Размер пула потоков
    """
    global _threads_pool
    
    async with _pool_lock:
        logger.info(f"Initializing OpenAI thread pool with {size} threads")
        for _ in range(size):
            try:
                thread = client.beta.threads.create()
                _threads_pool.append(thread.id)
                logger.debug(f"Created thread: {thread.id}")
                # Небольшая задержка чтобы не нагружать API
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"Error creating thread: {e}")
        
        logger.info(f"Thread pool initialized with {len(_threads_pool)} threads")

async def get_thread(client) -> str:
    """
    Получить готовый thread из пула или создать новый.
    
    Args:
        client: OpenAI API клиент
        
    Returns:
        str: ID потока
    """
    global _threads_pool, _last_refill
    
    # Пробуем взять thread из пула
    async with _pool_lock:
        if _threads_pool:
            thread_id = _threads_pool.pop()
            logger.debug(f"Using thread from pool: {thread_id}")
            
            # Проверяем, нужно ли пополнить пул
            now = time.time()
            if len(_threads_pool) <= POOL_SIZE // 2 and now - _last_refill > REFILL_INTERVAL:
                _last_refill = now
                asyncio.create_task(_refill_pool(client))
                
            return thread_id
    
    # Если пул пуст, создаем новый thread
    try:
        thread = client.beta.threads.create()
        logger.info(f"Created new thread outside pool: {thread.id}")
        return thread.id
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise

async def _refill_pool(client, count: int = POOL_SIZE // 2):
    """
    Асинхронно пополнить пул в фоновом режиме.
    
    Args:
        client: OpenAI API клиент
        count: Количество потоков для добавления
    """
    global _threads_pool
    
    logger.info(f"Refilling thread pool with {count} threads")
    new_threads = []
    
    for _ in range(count):
        try:
            thread = client.beta.threads.create()
            new_threads.append(thread.id)
            logger.debug(f"Added thread to pool: {thread.id}")
            # Небольшая задержка чтобы не нагружать API
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Error refilling pool: {e}")
    
    async with _pool_lock:
        _threads_pool.extend(new_threads)
        logger.info(f"Pool refilled, current size: {len(_threads_pool)}")

def get_pool_size() -> int:
    """
    Получить текущий размер пула.
    
    Returns:
        int: Количество доступных потоков в пуле
    """
    return len(_threads_pool)