"""
Модуль декораторов для API запросов и обработки ошибок.

Этот модуль предоставляет набор декораторов и утилит для:
1. Стандартизации обработки ошибок API
2. Автоматического повтора запросов с экспоненциальной задержкой
3. Отслеживания прогресса многоэтапных операций
4. Предоставления пользователю понятной информации о ходе выполнения запросов

Основные компоненты:
- ErrorType: Перечисление для категоризации ошибок API
- classify_error: Функция для классификации ошибок и создания дружественных сообщений
- with_retry_backoff: Декоратор для синхронных функций, добавляющий механизм повтора запросов
- with_async_retry_backoff: Декоратор для асинхронных функций с повтором запросов
- with_progress_stages: Декоратор для отслеживания многоэтапных операций
- update_stage: Утилита для обновления статуса выполнения этапа операции

Примеры использования:

1. Повтор запросов для синхронных функций:
   ```python
   @with_retry_backoff(max_retries=3, initial_backoff=1.0)
   def call_api(data):
       response = requests.post('https://api.example.com', json=data)
       response.raise_for_status()
       return response.json()
   ```

2. Повтор запросов для асинхронных функций:
   ```python
   @with_async_retry_backoff(max_retries=3, initial_backoff=1.0)
   async def call_api_async(data):
       async with aiohttp.ClientSession() as session:
           async with session.post('https://api.example.com', json=data) as response:
               response.raise_for_status()
               return await response.json()
   ```

3. Отслеживание прогресса многоэтапных операций:
   ```python
   @with_progress_stages(stages={
       "download": "Загрузка файла",
       "process": "Обработка данных",
       "upload": "Сохранение результатов"
   })
   async def process_file(file_path, **kwargs):
       # Загрузка
       data = await download_file(file_path)
       update_stage("download", kwargs, update_func)

       # Обработка
       result = process_data(data)
       update_stage("process", kwargs, update_func)

       # Сохранение
       await save_results(result)
       update_stage("upload", kwargs, update_func)

       return result
   ```
"""

import asyncio
import functools
import logging
import time
import uuid
from typing import Callable, TypeVar, Optional, Any, Dict, Tuple


class FriendlyException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.friendly_message = message


# Type variables for function signatures
T = TypeVar("T")  # For return type
P = TypeVar("P")  # For parameter types


# Error classification
class ErrorType:
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    SERVER = "server"
    CLIENT = "client"
    NETWORK = "network"
    UNKNOWN = "unknown"


def classify_error(error: Exception) -> Tuple[str, str]:
    """
    Классифицирует ошибку API для соответствующей обработки.

    Args:
        error: Исключение, которое нужно классифицировать

    Returns:
        tuple: (тип_ошибки, user_friendly_message)
    """
    error_str = str(error).lower()

    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return (
            ErrorType.TIMEOUT,
            "Сервис не ответил вовремя. Пожалуйста, попробуйте еще раз.",
        )

    # Rate limiting
    if any(
        x in error_str for x in [
            "rate limit", "ratelimit", "too many requests", "429"
        ]
    ): 
        return (
            ErrorType.RATE_LIMIT,
            "Сервис временно перегружен. Пожалуйста, попробуйте через минуту.",
        )

    # Authentication errors
    if any(
        x in error_str
        for x in ["authentication", "auth", "unauthorized", "api key", "401"]
    ):
        return (
            ErrorType.AUTHENTICATION,
            "Ошибка авторизации API. Пожалуйста, обратитесь к разработчикам.",
        )

    # Validation errors
    if any(
        x in error_str for x in [
            "validation", "invalid", "schema", "format", "400"
        ]
    ): 
        return (
            ErrorType.VALIDATION,
            "Неверный формат данных. Проверьте загруженный файл.",
        )

    # Server errors
    if any(
        x in error_str for x in ["server error", "500", "502", "503", "504"]
    ):
        return (
            ErrorType.SERVER,
            "Ошибка на стороне сервера. Пожалуйста, попробуйте позже.",
        )

    # Client errors
    if any(x in error_str for x in ["client error", "bad request"]):
        return (
            ErrorType.CLIENT,
            "Некорректный запрос. Попробуйте другой файл или формат.",
        )

    # Network errors
    if any(
        x in error_str for x in ["network", "connection", "connect", "unreachable"]
    ):
        return (
            ErrorType.NETWORK,
            "Проблемы с сетевым подключением. Проверьте соединение.",
        )

    # Default unknown
    return (ErrorType.UNKNOWN, "Неизвестная ошибка. Пожалуйста, попробуйте еще раз.")


def with_retry_backoff(
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    backoff_factor: float = 2.0,
    error_types: Optional[list] = None,
) -> Callable:
    """
    Декоратор для обычных (не async) функций, добавляющий повторные попытки
    с экспоненциальной задержкой.

    Args:
        max_retries: Максимальное количество повторных попыток
        initial_backoff: Начальная задержка в секундах
        backoff_factor: Множитель для экспоненциальной задержки
        error_types: Список типов ошибок для повторных попыток (None для всех)

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Генерируем ID запроса для логирования
            req_id = kwargs.pop("_req_id", uuid.uuid4().hex[:8])
            logger = logging.getLogger(func.__module__)

            retries = 0
            last_error = None

            while retries <= max_retries:
                try:
                    if retries > 0:
                        logger.info(
                            f"[{req_id}] Retry {retries}/{max_retries} for {func.__name__}"
                        )

                    return func(*args, **kwargs)

                except Exception as e:
                    error_class, friendly_msg = classify_error(e)
                    
                    # Улучшенное логирование для отладки - показываем всю цепочку ошибок
                    logger.error(f"[{req_id}] Exception: {e.__class__.__name__}: {str(e)}")
                    if hasattr(e, '__cause__') and e.__cause__:
                        cause = e.__cause__
                        logger.error(f"[{req_id}] Caused by: {cause.__class__.__name__}: {str(cause)}")
                        if hasattr(cause, '__cause__') and cause.__cause__:
                            root = cause.__cause__
                            logger.error(f"[{req_id}] Root cause: {root.__class__.__name__}: {str(root)}")
                    
                    # Детальный стектрейс
                    import traceback
                    logger.error(f"[{req_id}] Full stacktrace:\n{traceback.format_exc()}")
                    
                    # Проверяем, нужно ли повторить попытку для этого типа ошибок
                    if error_types and error_class not in error_types:
                        if retries > 0:
                            logger.info(
                                f"[{req_id}] Not retrying {error_class} error (not in retry types)"
                            )
                        raise

                    # Рассчитываем backoff
                    current_backoff = initial_backoff * (backoff_factor ** retries)

                    # Проверяем, нужно ли повторять попытку
                    if retries < max_retries:
                        logger.warning(
                            f"[{req_id}] {error_class} error in {func.__name__}: {str(e)}. "
                            f"Retrying in {current_backoff:.1f}s ({retries+1}/{max_retries})"
                        )
                        time.sleep(current_backoff)
                        retries += 1
                        last_error = e
                    else:
                        if retries > 0:
                            logger.error(
                                f"[{req_id}] {error_class} error in {func.__name__} after {retries} retries: {str(e)}"
                            )
                        else:
                            logger.error(
                                f"[{req_id}] {error_class} error in {func.__name__}: {str(e)}"
                            )

                        # Оборачиваем ошибку с понятным сообщением
                        if hasattr(e, "friendly_message"):
                            raise type(e)(e.friendly_message) from e
                        else:
                            e.friendly_message = friendly_msg
                            # Добавляем фактическую ошибку в сообщение для более простой диагностики
                            if error_class == ErrorType.UNKNOWN:
                                enhanced_msg = f"{friendly_msg} ({e.__class__.__name__}: {str(e)})"
                                raise RuntimeError(enhanced_msg) from e
                            else:
                                raise RuntimeError(friendly_msg) from e

            # Никогда не должны сюда попасть, но на всякий случай
            if last_error:
                raise last_error
            raise RuntimeError(
                f"[{req_id}] Unexpected error in retry logic for {func.__name__}"
            )

        return wrapper

    return decorator


def with_async_retry_backoff(
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    backoff_factor: float = 2.0,
    error_types: Optional[list] = None,
) -> Callable:
    """
    Декоратор для асинхронных функций, добавляющий повторные попытки с экспоненциальной задержкой.

    Args:
        max_retries: Максимальное количество повторных попыток
        initial_backoff: Начальная задержка в секундах
        backoff_factor: Множитель для экспоненциальной задержки
        error_types: Список типов ошибок для повторных попыток (None для всех)

    Returns:
        Decorated async function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Генерируем ID запроса для логирования
            req_id = kwargs.pop("_req_id", uuid.uuid4().hex[:8])
            logger = logging.getLogger(func.__module__)

            retries = 0
            last_error = None

            while retries <= max_retries:
                try:
                    if retries > 0:
                        logger.info(
                            f"[{req_id}] Retry {retries}/{max_retries} for {func.__name__}"
                        )

                    return await func(*args, **kwargs)

                except Exception as e:
                    error_class, friendly_msg = classify_error(e)
                    current_backoff = initial_backoff * (backoff_factor**retries)

                    # Проверяем, нужно ли повторять для этого типа ошибки
                    can_retry = error_types is None or error_class in error_types

                    # Не повторяем для ошибок валидации и авторизации
                    if error_class in [ErrorType.VALIDATION, ErrorType.AUTHENTICATION]:
                        can_retry = False

                    if can_retry and retries < max_retries:
                        logger.warning(
                            f"[{req_id}] {error_class} error in {func.__name__}: {str(e)}. "
                            f"Retrying in {current_backoff:.1f}s ({retries+1}/{max_retries})"
                        )
                        await asyncio.sleep(current_backoff)
                        retries += 1
                        last_error = e
                    else:
                        if retries > 0:
                            logger.error(
                                f"[{req_id}] {error_class} error in {func.__name__} after {retries} retries: {str(e)}"
                            )
                        else:
                            logger.error(
                                f"[{req_id}] {error_class} error in {func.__name__}: {str(e)}"
                            )

                        # Оборачиваем ошибку с понятным сообщением
                        if hasattr(e, "friendly_message"):
                            raise type(e)(e.friendly_message) from e
                        else:
                            e.friendly_message = friendly_msg
                            raise RuntimeError(friendly_msg) from e

            # Никогда не должны сюда попасть, но на всякий случай
            if last_error:
                raise last_error
            raise RuntimeError(
                f"[{req_id}] Unexpected error in retry logic for {func.__name__}"
            )

        return wrapper

    return decorator


def with_progress_stages(stages: Dict[str, str]) -> Callable:
    """
    Декоратор для асинхронных функций, добавляющий отслеживание прогресса по этапам.
    Настраивает отображение прогресса для UI и ведение логов по стадиям.

    Args:
        stages: Словарь с этапами и их описаниями для UI

    Returns:
        Decorated async function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Получаем или создаем ID запроса для логирования
            req_id = kwargs.pop("_req_id", uuid.uuid4().hex[:8])
            logger = logging.getLogger(func.__module__)

            # Создаем словарь для отслеживания состояния этапов
            stages_state = {stage: False for stage in stages.keys()}
            error_stage = None

            # Добавляем информацию о стадиях в контекст выполнения
            kwargs["_stages"] = stages_state
            kwargs["_stages_names"] = stages
            kwargs["_req_id"] = req_id

            # Функция обновления прогресса - может быть переопределена при вызове
            update_progress = kwargs.pop("_update_progress", None)

            try:
                # Запускаем основную функцию
                t0 = time.time()
                result = await func(*args, **kwargs)
                total_time = time.time() - t0

                logger.info(
                    f"[{req_id}] '{func.__name__}' completed in {total_time:.2f}s"
                )
                return result

            except Exception as e:
                # Определяем, на каком этапе произошла ошибка
                error_stage = next(
                    (stage for stage, done in stages_state.items() if not done), None
                )

                # Классифицируем ошибку
                error_class, friendly_msg = classify_error(e)

                # Логируем ошибку с контекстом этапа
                if error_stage:
                    stage_name = stages.get(error_stage, error_stage)
                    logger.error(
                        f"[{req_id}] {error_class} error in {func.__name__} at stage "
                        f"'{stage_name}': {str(e)}"
                    )

                    # Добавляем информацию о стадии в ошибку
                    friendly_msg = (
                        f"Ошибка на этапе '{stage_name}': {friendly_msg}"
                    )
                else:
                    logger.error(
                        f"[{req_id}] {error_class} error in {func.__name__}: {str(e)}"
                    )

                # Обновляем UI с информацией об ошибке, если есть функция
                if update_progress:
                    try:
                        await update_progress(
                            error_message=friendly_msg, stage=error_stage
                        )
                    except Exception as ui_err:
                        logger.warning(
                            f"[{req_id}] Failed to update UI with error: {ui_err}"
                        )

                # Пробрасываем ошибку дальше
                if isinstance(e, FriendlyException):
                    raise e
                else:
                    raise FriendlyException(friendly_msg) from e

        return wrapper

    return decorator


def update_stage(stage: str, context: dict, update_func=None) -> None:
    """
    Утилита для обновления стадии выполнения внутри декорированной функции.

    Args:
        stage: Ключ стадии для обновления
        context: Словарь контекста с _stages и _stages_names
        update_func: Необязательная функция для обновления UI
    """
    if "_stages" not in context or "_stages_names" not in context:
        return

    # Обновляем состояние стадии
    if stage in context["_stages"]:
        context["_stages"][stage] = True

        # Вызываем функцию обновления UI, если она есть
        if update_func and callable(update_func):
            stage_name = context["_stages_names"].get(stage, stage)
            try:
                if asyncio.iscoroutinefunction(update_func):
                    # Нельзя напрямую вызвать await, создаем задачу
                    asyncio.create_task(
                        update_func(stage=stage, stage_name=stage_name)
                    )
                else:
                    update_func(stage=stage, stage_name=stage_name)
            except Exception:
                # Игнорируем ошибки UI, чтобы не прервать основную логику
                pass
