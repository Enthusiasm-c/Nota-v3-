"""
Модуль для расширенного логирования и диагностики проблем OCR.
"""

import importlib.util
import json
import logging
import os
import time
import traceback
from datetime import date, datetime
from functools import wraps

# Импортируем ParsedData для типизации
from app.models import ParsedData

# --- Опциональный импорт psutil ---
try:
    PSUTIL_AVAILABLE = bool(importlib.util.find_spec("psutil"))
except ImportError:
    PSUTIL_AVAILABLE = False

# Создаем директорию для логов, если её нет
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
)
os.makedirs(LOG_DIR, exist_ok=True)

# Устанавливаем специальный логгер для OCR с записью в файл
ocr_logger = logging.getLogger("ocr_debug")
ocr_logger.setLevel(logging.DEBUG)

# Создаем файловый обработчик, который будет записывать логи в отдельный файл
log_file = os.path.join(LOG_DIR, f'ocr_detailed_{datetime.now().strftime("%Y%m%d")}.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# Форматирование логов
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

# Добавляем обработчик к логгеру
ocr_logger.addHandler(file_handler)
ocr_logger.propagate = False  # Чтобы избежать дублирования в основной лог


def json_serialize(obj):
    """
    Функция-сериализатор для преобразования объектов в JSON.
    Обрабатывает типы date и datetime.
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def log_ocr_call(func):
    """
    Декоратор для логирования OCR вызовов с детальной информацией
    о времени выполнения, размере входных данных и результатах.
    """

    @wraps(func)
    def wrapper(image_bytes, *args, **kwargs):
        request_id = kwargs.get("_req_id", f"ocr_{int(time.time())}")

        # Логируем начало запроса
        ocr_logger.info(
            f"[{request_id}] OCR запрос начат: размер изображения = {len(image_bytes)} байт"
        )
        start_time = time.time()

        try:
            # Выполняем OCR-запрос
            result = func(image_bytes, *args, **kwargs)

            # Логируем успешное завершение
            elapsed = time.time() - start_time
            ocr_logger.info(f"[{request_id}] OCR запрос успешно завершен за {elapsed:.2f} сек")

            # Логируем результат
            if hasattr(result, "model_dump"):
                # Для Pydantic моделей v2
                result_dict = result.model_dump()
                positions_count = len(result_dict.get("positions", []))
                ocr_logger.debug(f"[{request_id}] Найдено позиций: {positions_count}")

                # Ограничиваем вывод для избежания слишком больших логов
                log_result = {
                    "supplier": result_dict.get("supplier"),
                    "date": result_dict.get("date"),
                    "total_price": result_dict.get("total_price"),
                    "positions_count": positions_count,
                    "has_empty_positions": any(
                        not p.get("name") for p in result_dict.get("positions", [])
                    ),
                }
                ocr_logger.debug(
                    f"[{request_id}] Результат OCR: {json.dumps(log_result, default=json_serialize)}"
                )
            else:
                ocr_logger.debug(f"[{request_id}] Результат OCR: {result}")

            # Журналируем успешный результат
            if log_file and isinstance(result, ParsedData):
                try:
                    # Используем model_dump() вместо устаревшего dict()
                    result_dict = result.model_dump()
                    with open(log_file, "w", encoding="utf-8") as f:
                        json.dump(
                            result_dict, f, indent=2, ensure_ascii=False, default=json_serialize
                        )
                except Exception as e:
                    logging.error(f"Failed to save OCR result to file: {e}")

            return result

        except Exception as e:
            # Логируем ошибку с полным стектрейсом
            elapsed = time.time() - start_time
            ocr_logger.error(
                f"[{request_id}] OCR запрос завершился с ошибкой после {elapsed:.2f} сек: {str(e)}"
            )
            ocr_logger.error(f"[{request_id}] Стектрейс: {traceback.format_exc()}")

            # Пробрасываем исключение дальше
            raise

    return wrapper


def log_ocr_performance(start_time=None, label=None, request_id=None):
    """
    Вспомогательная функция для логирования промежуточных шагов обработки OCR.
    """
    current_time = time.time()

    if start_time is not None and label is not None:
        elapsed = current_time - start_time
        req_id = request_id or "unknown"
        ocr_logger.debug(f"[{req_id}] PERFORMANCE: {label} - {elapsed:.4f} сек")

    return current_time


def create_memory_monitor(interval=10.0):
    """
    Создает отдельный поток, который будет мониторить использование памяти
    во время выполнения OCR-запросов.
    """
    if not PSUTIL_AVAILABLE:

        def create_dummy_thread(request_id):
            class DummyThread:
                def start(self):
                    ocr_logger.debug(f"[{request_id}] MEMORY: мониторинг отключен (нет psutil)")

            return DummyThread()

        return create_dummy_thread
    try:
        import os
        import threading

        import psutil

        def monitor_memory(request_id):
            process = psutil.Process(os.getpid())

            try:
                while True:
                    mem_info = process.memory_info()
                    mem_mb = mem_info.rss / (1024 * 1024)
                    ocr_logger.debug(f"[{request_id}] MEMORY: {mem_mb:.2f} MB используется")
                    time.sleep(interval)
            except Exception as e:
                # Просто завершаем поток с логированием ошибки
                ocr_logger.debug(f"[{request_id}] Ошибка мониторинга памяти: {str(e)}")
                pass

        def create_thread(request_id):
            thread = threading.Thread(target=monitor_memory, args=(request_id,))
            thread.daemon = True  # Завершится автоматически с основным потоком
            return thread

        return create_thread

    except (ImportError, AttributeError) as e:
        # Если psutil не установлен или не работает корректно, возвращаем заглушку
        ocr_logger.warning(f"Модуль psutil недоступен: {str(e)}, мониторинг памяти отключен")

        def create_dummy_thread(request_id):
            class DummyThread:
                def start(self):
                    ocr_logger.debug(f"[{request_id}] MEMORY: мониторинг отключен (нет psutil)")

            return DummyThread()

        return create_dummy_thread
