"""
Модуль для управления пулом потоков OpenAI с оптимизациями скорости.
Создает и поддерживает пул предварительно инициализированных потоков для ускорения обработки запросов.
"""

import asyncio
import logging
import random
from typing import List, Set

from app.utils.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Максимальное количество потоков в пуле
MAX_POOL_SIZE = 8  # 8 потоков в пуле

# Ключ для хранения пула в Redis
POOL_KEY = "openai:thread_pool"

# Время жизни потока в пуле (в секундах)
THREAD_TTL = 3600  # 1 час

# Set для отслеживания потоков в процессе создания
creating_threads: Set[str] = set()


async def initialize_pool(client, size: int = MAX_POOL_SIZE) -> List[str]:
    """
    Предварительно создает пул потоков OpenAI для быстрого использования

    Args:
        client: OpenAI клиент
        size: Желаемый размер пула

    Returns:
        List[str]: Список идентификаторов созданных потоков
    """
    logger.info(f"Инициализация пула потоков OpenAI, размер: {size}")

    # Проверяем, существует ли уже пул в Redis
    pool = cache_get(POOL_KEY)
    if pool:
        try:
            thread_ids = pool.split(",")
            logger.info(f"Загружен существующий пул потоков: {len(thread_ids)} потоков")

            # Проверяем, нужны ли дополнительные потоки
            if len(thread_ids) >= size:
                return thread_ids[:size]

            # Создаем дополнительные потоки до требуемого размера
            needed = size - len(thread_ids)
            logger.info(f"Требуется создать еще {needed} потоков")

            new_threads = []
            for _ in range(needed):
                thread_id = await create_thread(client)
                new_threads.append(thread_id)

            # Обновляем пул в Redis
            updated_pool = thread_ids + new_threads
            cache_set(POOL_KEY, ",".join(updated_pool), ex=THREAD_TTL)

            return updated_pool
        except Exception as e:
            logger.error(f"Ошибка при загрузке пула из Redis: {e}")

    # Создаем новый пул
    thread_ids = []
    for i in range(size):
        try:
            thread_id = await create_thread(client)
            thread_ids.append(thread_id)
        except Exception as e:
            logger.error(f"Ошибка при создании потока {i}: {e}")

    # Сохраняем пул в Redis
    if thread_ids:
        cache_set(POOL_KEY, ",".join(thread_ids), ex=THREAD_TTL)

    logger.info(f"Пул потоков создан, размер: {len(thread_ids)}")
    return thread_ids


async def create_thread(client) -> str:
    """
    Создает новый поток OpenAI

    Args:
        client: OpenAI клиент

    Returns:
        str: Идентификатор созданного потока
    """
    logger.debug("Создание нового потока OpenAI")
    # По возможности использовать асинхронный вызов для скорости
    thread = await asyncio.to_thread(client.beta.threads.create)
    thread_id = thread.id
    logger.debug(f"Создан новый поток: {thread_id}")
    return thread_id


async def get_thread(client) -> str:
    """
    Получает поток из пула или создает новый для использования

    Args:
        client: OpenAI клиент

    Returns:
        str: Идентификатор потока для использования
    """
    # Проверяем пул в Redis
    pool = cache_get(POOL_KEY)

    if pool:
        thread_ids = pool.split(",")
        if thread_ids:
            # Выбираем случайный поток из пула для равномерной нагрузки
            thread_id = random.choice(thread_ids)

            # Удаляем выбранный поток из пула
            thread_ids.remove(thread_id)

            # Обновляем пул в Redis
            if thread_ids:
                cache_set(POOL_KEY, ",".join(thread_ids), ex=THREAD_TTL)
            else:
                # Если пул пуст, удаляем ключ
                cache_set(POOL_KEY, "", ex=1)

            # Асинхронно пополняем пул
            asyncio.create_task(refill_pool(client))

            return thread_id

    # Если пул пуст или не существует, создаем новый поток
    return await create_thread(client)


async def refill_pool(client, target_size: int = MAX_POOL_SIZE) -> None:
    """
    Асинхронно пополняет пул потоков до целевого размера

    Args:
        client: OpenAI клиент
        target_size: Целевой размер пула
    """
    pool = cache_get(POOL_KEY)
    current_size = 0

    if pool:
        thread_ids = pool.split(",")
        current_size = len(thread_ids)

    if current_size >= target_size:
        return

    # Создаем новые потоки асинхронно
    needed = target_size - current_size
    new_threads = []

    for _ in range(needed):
        try:
            thread_id = await create_thread(client)
            new_threads.append(thread_id)
        except Exception as e:
            logger.error(f"Ошибка при пополнении пула: {e}")

    # Обновляем пул в Redis
    if new_threads:
        all_threads = (thread_ids if pool else []) + new_threads
        cache_set(POOL_KEY, ",".join(all_threads), ex=THREAD_TTL)

    logger.debug(
        f"Пул пополнен: добавлено {len(new_threads)} потоков, всего {current_size + len(new_threads)}"
    )


def release_thread(thread_id: str) -> None:
    """
    Возвращает поток обратно в пул для повторного использования

    Args:
        thread_id: Идентификатор потока для возврата в пул
    """
    if not thread_id:
        return

    # Проверяем пул в Redis
    pool = cache_get(POOL_KEY)
    thread_ids = []

    if pool:
        thread_ids = pool.split(",")

    # Добавляем поток обратно в пул, если он еще не там
    if thread_id not in thread_ids:
        thread_ids.append(thread_id)
        cache_set(POOL_KEY, ",".join(thread_ids), ex=THREAD_TTL)
        logger.debug(f"Поток {thread_id} возвращен в пул, размер пула: {len(thread_ids)}")


async def shutdown_thread_pool() -> None:
    """
    Gracefully shuts down the thread pool and releases resources.
    Should be called during application shutdown.
    """
    logger.info("Shutting down OpenAI thread pool")

    try:
        # Clear pool from Redis
        pool = cache_get(POOL_KEY)
        if pool:
            logger.info("Clearing thread pool from Redis")
            cache_set(POOL_KEY, "", ex=1)  # Set empty with 1s TTL (effectively delete)
    except Exception as e:
        logger.error(f"Error clearing thread pool from Redis: {e}")

    # Wait a moment to ensure any pending operations complete
    await asyncio.sleep(0.5)

    logger.info("Thread pool shutdown complete")
