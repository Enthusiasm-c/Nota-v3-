"""
Модуль для защиты от повторной обработки запросов пользователя.
Предотвращает многократную обработку одного и того же запроса.
"""

import asyncio
import logging
import time
from typing import Dict, Set, Any, Optional, Callable, Awaitable
import functools

logger = logging.getLogger(__name__)

# Множество активных пользователей с временными метками
_active_users: Dict[int, Dict[str, Any]] = {}

# Множество пользователей в процессе обработки фото
_processing_photo_users: Set[int] = set()

# Отдельное множество для пользователей в процессе отправки в Syrve
_sending_to_syrve_users: Set[int] = set()

# Множество пользователей для отслеживания частых запросов
_user_request_timestamps: Dict[int, Dict[str, float]] = {}

# Словари для хранения блокировок
_processing_photo: Dict[int, bool] = {}
_sending_to_syrve: Dict[int, bool] = {}
_processing_edit: Dict[int, bool] = {}

# Таймауты для автоматического снятия блокировок
PHOTO_TIMEOUT = 60  # 60 секунд
SYRVE_TIMEOUT = 30  # 30 секунд
EDIT_TIMEOUT = 15   # 15 секунд

async def check_user_busy(user_id: int, context_name: str = "default") -> bool:
    """
    Проверяет, занят ли пользователь обработкой другого запроса.
    
    Args:
        user_id: ID пользователя
        context_name: Имя контекста запроса для разделения типов запросов
        
    Returns:
        True, если пользователь занят, False в противном случае
    """
    # Проверяем, активен ли пользователь в данном контексте
    if user_id in _active_users and context_name in _active_users[user_id]:
        # Проверяем, не истекло ли время блокировки (по умолчанию 2 минуты)
        last_activity = _active_users[user_id][context_name]["timestamp"]
        max_age = _active_users[user_id][context_name].get("max_age", 120)  # 2 минуты по умолчанию
        
        if time.time() - last_activity < max_age:
            logger.warning(f"User {user_id} blocked in context {context_name}: already processing")
            return True
        else:
            # Тайм-аут истек, снимаем блокировку
            logger.info(f"User {user_id} lock in context {context_name} expired after {max_age}s")
            if context_name in _active_users[user_id]:
                del _active_users[user_id][context_name]
                
    return False

async def set_user_busy(user_id: int, context_name: str = "default", max_age: int = 120) -> None:
    """
    Устанавливает состояние "занят" для пользователя.
    
    Args:
        user_id: ID пользователя
        context_name: Имя контекста запроса
        max_age: Максимальное время блокировки в секундах
    """
    if user_id not in _active_users:
        _active_users[user_id] = {}
        
    _active_users[user_id][context_name] = {
        "timestamp": time.time(),
        "max_age": max_age
    }
    
    logger.debug(f"User {user_id} marked as busy in context {context_name}")

async def set_user_free(user_id: int, context_name: str = "default") -> None:
    """
    Снимает состояние "занят" для пользователя.
    
    Args:
        user_id: ID пользователя
        context_name: Имя контекста запроса
    """
    if user_id in _active_users and context_name in _active_users[user_id]:
        del _active_users[user_id][context_name]
        
        if not _active_users[user_id]:
            del _active_users[user_id]
            
        logger.debug(f"User {user_id} marked as free in context {context_name}")

# --- Функции для обработки фотографий ---

async def is_processing_photo(user_id: int) -> bool:
    """
    Проверяет, обрабатывает ли пользователь фотографию в данный момент.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        True, если пользователь обрабатывает фото, False в противном случае
    """
    return _processing_photo.get(user_id, False)

async def set_processing_photo(user_id: int, state: bool) -> None:
    """Установить флаг обработки фото для пользователя."""
    _processing_photo[user_id] = state
    if state:
        asyncio.create_task(_auto_clear_photo(user_id))

async def _auto_clear_photo(user_id: int) -> None:
    """Автоматически снять блокировку обработки фото через таймаут."""
    await asyncio.sleep(PHOTO_TIMEOUT)
    _processing_photo.pop(user_id, None)

# --- Функции для отправки в Syrve ---

async def is_sending_to_syrve(user_id: int) -> bool:
    """
    Проверяет, отправляет ли пользователь данные в Syrve в данный момент.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        True, если пользователь отправляет данные в Syrve
    """
    return _sending_to_syrve.get(user_id, False)

async def set_sending_to_syrve(user_id: int, state: bool) -> None:
    """Установить флаг отправки в Syrve для пользователя."""
    _sending_to_syrve[user_id] = state
    if state:
        asyncio.create_task(_auto_clear_syrve(user_id))

async def _auto_clear_syrve(user_id: int) -> None:
    """Автоматически снять блокировку отправки в Syrve через таймаут."""
    await asyncio.sleep(SYRVE_TIMEOUT)
    _sending_to_syrve.pop(user_id, None)

# --- Функции для редактирования инвойса ---

async def is_processing_edit(user_id: int) -> bool:
    """
    Проверяет, редактирует ли пользователь инвойс в данный момент.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        True, если пользователь редактирует инвойс
    """
    return _processing_edit.get(user_id, False)

async def set_processing_edit(user_id: int, state: bool) -> None:
    """
    Установить флаг редактирования для пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        state: True для установки флага, False для снятия
    """
    logger.debug(f"set_processing_edit: user_id={user_id}, state={state}")
    _processing_edit[user_id] = state
    if state:
        # Запускаем задачу автоматической очистки флага через EDIT_TIMEOUT секунд
        asyncio.create_task(_auto_clear_edit(user_id))

async def _auto_clear_edit(user_id: int) -> None:
    """Автоматически снять блокировку редактирования через таймаут."""
    await asyncio.sleep(EDIT_TIMEOUT)
    if user_id in _processing_edit:
        prev_state = _processing_edit.get(user_id)
        _processing_edit.pop(user_id, None)
        logger.debug(f"Автоочистка блокировки редактирования для user_id={user_id}, prev_state={prev_state}")

# --- Защита от частых запросов ---

async def check_rate_limit(user_id: int, action_type: str, 
                          min_interval: float = 2.0, 
                          notify: bool = False) -> bool:
    """
    Проверяет ограничение частоты запросов для пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        action_type: Тип действия для разделения ограничений
        min_interval: Минимальный интервал между запросами в секундах
        notify: Записывать ли предупреждение в лог
        
    Returns:
        True, если запрос можно обработать, False если слишком частый
    """
    current_time = time.time()
    
    if user_id not in _user_request_timestamps:
        _user_request_timestamps[user_id] = {}
        
    if action_type in _user_request_timestamps[user_id]:
        last_request = _user_request_timestamps[user_id][action_type]
        elapsed = current_time - last_request
        
        if elapsed < min_interval:
            if notify:
                logger.warning(f"Rate limit for user {user_id} on {action_type}: {elapsed:.2f}s < {min_interval}s")
            return False
    
    # Обновляем временную метку
    _user_request_timestamps[user_id][action_type] = current_time
    return True

# --- Декораторы ---

def require_user_free(context_name: str = "default", max_age: int = 120):
    """
    Декоратор для проверки, что пользователь не занят другим запросом.
    
    Args:
        context_name: Имя контекста запроса
        max_age: Максимальное время блокировки в секундах
        
    Returns:
        Декоратор для асинхронной функции
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Ищем user_id в аргументах
            user_id = None
            
            # Ищем в первом аргументе message или call, которые имеют from_user.id
            if args and hasattr(args[0], 'from_user') and hasattr(args[0].from_user, 'id'):
                user_id = args[0].from_user.id
            # Ищем в аргументе user_id
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            # Ищем в state
            elif 'state' in kwargs and hasattr(kwargs['state'], 'user'):
                user_id = kwargs['state'].user
                
            if user_id is None:
                logger.warning("Cannot find user_id in arguments, bypass protection")
                # Если не можем найти user_id, пропускаем защиту
                return await func(*args, **kwargs)
                
            # Проверяем, занят ли пользователь
            if await check_user_busy(user_id, context_name):
                logger.warning(f"User {user_id} is busy in context {context_name}, request ignored")
                
                # Можно вернуть сообщение о том, что запрос игнорируется
                if hasattr(args[0], 'answer'):
                    await args[0].answer("Предыдущий запрос еще обрабатывается. Пожалуйста, подождите.")
                elif hasattr(args[0], 'reply'):
                    await args[0].reply("Предыдущий запрос еще обрабатывается. Пожалуйста, подождите.")
                    
                return None
                
            # Помечаем пользователя как занятого
            await set_user_busy(user_id, context_name, max_age)
            
            try:
                # Вызываем оригинальную функцию
                result = await func(*args, **kwargs)
                return result
            finally:
                # В любом случае помечаем пользователя как свободного
                await set_user_free(user_id, context_name)
                
        return wrapper
    return decorator

def require_rate_limit(action_type: str, min_interval: float = 2.0):
    """
    Декоратор для ограничения частоты запросов.
    
    Args:
        action_type: Тип действия для разделения ограничений
        min_interval: Минимальный интервал между запросами в секундах
        
    Returns:
        Декоратор для асинхронной функции
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Ищем user_id в аргументах
            user_id = None
            
            # Ищем в первом аргументе message или call, которые имеют from_user.id
            if args and hasattr(args[0], 'from_user') and hasattr(args[0].from_user, 'id'):
                user_id = args[0].from_user.id
            # Ищем в аргументе user_id
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            # Ищем в state
            elif 'state' in kwargs and hasattr(kwargs['state'], 'user'):
                user_id = kwargs['state'].user
                
            if user_id is None:
                logger.warning("Cannot find user_id in arguments, bypass rate limit")
                # Если не можем найти user_id, пропускаем защиту
                return await func(*args, **kwargs)
                
            # Проверяем ограничение частоты
            if not await check_rate_limit(user_id, action_type, min_interval, notify=True):
                logger.warning(f"Rate limit exceeded for user {user_id} on {action_type}")
                
                # Можно вернуть сообщение о том, что запрос слишком частый
                if hasattr(args[0], 'answer'):
                    await args[0].answer("Слишком частые запросы. Пожалуйста, подождите.")
                elif hasattr(args[0], 'reply'):
                    await args[0].reply("Слишком частые запросы. Пожалуйста, подождите.")
                    
                return None
                
            # Вызываем оригинальную функцию
            return await func(*args, **kwargs)
                
        return wrapper
    return decorator

def clear_all_locks():
    """Очищает все блокировки и флаги пользователей."""
    global _active_users, _processing_photo_users, _sending_to_syrve_users, _user_request_timestamps
    
    _active_users.clear()
    _processing_photo_users.clear()
    _sending_to_syrve_users.clear()
    _user_request_timestamps.clear()
    
    # Более подробное логирование для отладки
    logger.info(f"All user locks and flags cleared: active_users={len(_active_users)}, photo_users={len(_processing_photo_users)}, syrve_users={len(_sending_to_syrve_users)}, request_timestamps={len(_user_request_timestamps)}")
    print(f"[GUARD] Cleared all locks: active_users={len(_active_users)}, photo_users={len(_processing_photo_users)}, syrve_users={len(_sending_to_syrve_users)}")
    
    _processing_photo.clear()
    _sending_to_syrve.clear()
    _processing_edit.clear()
    
    return True