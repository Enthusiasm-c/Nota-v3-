"""
OpenAI Assistant API клиент для Nota.
Предоставляет интерфейс для обработки текстовых команд через GPT-3.5-turbo.
"""

import json
import logging
import time
import re
import asyncio
from typing import Dict, Any, Optional, List, Union
import os
import openai
from app.config import settings
from app.assistants.trace_openai import trace_openai
from app.utils.redis_cache import cache_get, cache_set
from app.assistants.intent_adapter import adapt_intent
from app.assistants.thread_pool import get_thread, initialize_pool

from pydantic import BaseModel, ValidationError, field_validator
from functools import wraps

logger = logging.getLogger(__name__)

class EditCommand(BaseModel):
    action: str
    row: Optional[int] = None
    qty: Optional[Union[str, float, int]] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[Union[str, float, int]] = None
    price_per_unit: Optional[Union[str, float, int]] = None
    total_price: Optional[Union[str, float, int]] = None
    date: Optional[str] = None
    supplier: Optional[str] = None
    error: Optional[str] = None

    @field_validator('row')
    @classmethod
    def check_row(cls, v, values):
        # Только для команд, где row обязателен
        actions_with_row = {"set_name", "set_qty", "set_unit", "set_price", "set_price_per_unit", "set_total_price"}
        action = values.data.get("action")
        if action in actions_with_row:
            if v is None or v < 1:
                raise ValueError(f"row must be >= 1 for action {action}")
        return v

from app.utils.monitor import parse_action_monitor

__all__ = [
    "EditCommand",
    "parse_assistant_output",
    "run_thread_safe",
    "parse_edit_command",
    "adapt_intent",  # экспортируем функцию адаптера для удобства
]

def parse_edit_command(user_input: str, invoice_lines=None) -> list:
    """
    Универсальный парсер команд для инвойса. Используется как в тестах, так и в run_thread_safe.
    Поддерживает комбинированные команды (несколько команд в одном сообщении).
    
    Args:
        user_input: строка команды пользователя
        invoice_lines: (опционально) количество строк в инвойсе для проверки границ
        
    Returns:
        Список dict'ов с действиями
    """
    import re
    from datetime import datetime
    
    # First replace newlines with semicolons, then split by semicolons, commas, or periods
    # Улучшенное разбиение: сначала по \n, затем по ;, затем по разделителям с пробелом/концом строки
    lines = user_input.split('\n')
    commands = []
    for line in lines:
        # Сначала делим по ;
        semi_split = [c.strip() for c in line.split(';') if c.strip()]
        for semi in semi_split:
            # Теперь делим по запятым или точкам, если они стоят перед пробелом или концом строки
            parts = [c.strip() for c in re.split(r'[,.](?=\s|\Z)', semi) if c.strip()]
            commands.extend(parts)
    # If no commands found after splitting, try to process whole input
    if not commands and user_input.strip():
        commands = [user_input.strip()]
        
    results = []
    reserved_keywords = ['date', 'дата', 'supplier', 'поставщик', 'total', 'итог', 'line', 'row', 'строка']
    has_reserved_keywords = any(kw in user_input.lower() for kw in reserved_keywords)
    
    for cmd in commands:
        # --- Date ---
        # Check for date patterns first
        date_match = (
            re.search(r'(?:дата|date|invoice date)\s+([\d]{1,2})[.\/-]([\d]{1,2})[.\/-]([\d]{4}|\d{2})', cmd, re.IGNORECASE) or
            re.search(r'(?:дата|date|invoice date)\s+([\d]{4})[.\/-]([\d]{1,2})[.\/-]([\d]{1,2})', cmd, re.IGNORECASE) or
            re.search(r'(?:дата|date|invoice date)\s+([\d]{1,2})(?:\s+|-)?(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', cmd, re.IGNORECASE) or
            re.search(r'(?:дата|date|invoice date)\s+([\d]{1,2})(?:\s+|-)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)', cmd, re.IGNORECASE)
        )
        
        if date_match:
            try:
                # Define month name to number mappings
                ru_month_map = {
                    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
                    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
                    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
                }
                
                en_month_map = {
                    "january": 1, "february": 2, "march": 3, "april": 4,
                    "may": 5, "june": 6, "july": 7, "august": 8,
                    "september": 9, "october": 10, "november": 11, "december": 12,
                    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
                    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
                }
                
                # Check which format we matched
                if len(date_match.groups()) >= 2 and date_match.group(2):
                    month_name = date_match.group(2).lower()
                    
                    # Check if it's Russian or English month
                    if month_name in ru_month_map:
                        month = ru_month_map[month_name]
                    elif month_name in en_month_map:
                        month = en_month_map[month_name]
                    else:
                        raise ValueError(f"Unknown month name: {month_name}")
                        
                    # Get day and set current year
                    day = int(date_match.group(1))
                    year = datetime.now().year  # Current year if not specified
                    
                    # If month is in the past and it's not December, assume next year
                    current_month = datetime.now().month
                    if month < current_month and month != 12:
                        year += 1
                    
                elif len(date_match.groups()) >= 3:
                    if len(date_match.group(3)) == 4:  # DD.MM.YYYY
                        day = int(date_match.group(1))
                        month = int(date_match.group(2))
                        year = int(date_match.group(3))
                    elif len(date_match.group(1)) == 4:  # YYYY.MM.DD
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                    else:  # DD.MM.YY
                        day = int(date_match.group(1))
                        month = int(date_match.group(2))
                        year = 2000 + int(date_match.group(3))  # Assume 20xx for 2-digit years
                else:
                    raise ValueError("Invalid date format")
                
                # Format as YYYY-MM-DD (ISO format)
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                results.append({"action": "set_date", "date": date_str})
                continue
            except Exception as e:
                results.append({"action": "unknown", "error": f"invalid_date_format: {str(e)}"})
                continue
        
        # --- Supplier ---
        if (cmd.lower().startswith("поставщик ") or
            "изменить поставщика на" in cmd.lower() or
            cmd.lower().startswith("supplier ") or
            "change supplier to" in cmd.lower()):
            if cmd.lower().startswith("поставщик "):
                supplier = cmd[len("поставщик "):].strip()
            elif "изменить поставщика на" in cmd.lower():
                idx = cmd.lower().index("изменить поставщика на")
                supplier = cmd[idx+len("изменить поставщика на"):].strip()
            elif cmd.lower().startswith("supplier "):
                supplier = cmd[len("supplier "):].strip()
            else:
                idx = cmd.lower().index("change supplier to")
                supplier = cmd[idx+len("change supplier to"):].strip()
            results.append({"action": "set_supplier", "supplier": supplier})
            continue
        
        # --- Total ---
        # Improved total pattern matching
        match_total = re.search(r'(?:общая сумма|итого|total)\s*([\d,.]+(?:\s*[kкк])?)', cmd, re.IGNORECASE)
        if match_total:
            try:
                val = match_total.group(1).lower().strip()
                # Handle 'k' or 'к' suffix (thousands)
                has_k = 'k' in val or 'к' in val
                val = val.replace('k', '').replace('к', '')
                
                # Check that only one number (invalid format otherwise)
                if val.count(',') > 1 or val.count('.') > 1:
                    raise ValueError('invalid number format')
                
                total = float(val.replace(',', '.'))
                # Multiply by 1000 if 'k' suffix was present
                if has_k:
                    total *= 1000
                
                results.append({"action": "set_total", "total": total})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_total_value"})
            continue
        
        # --- Price ---
        # Handle price patterns with "per pack" or similar suffixes
        match_price = (
            re.search(r'(?:строка|line|row)\s*(-?\d+).*?(?:цена|price)\s*([\d.,]+(?:\s*[kкк])?)\s*(?:per\s+\w+|за.*)?', cmd, re.IGNORECASE) or
            re.search(r'(?:изменить цену в строке|change price in row)\s*(-?\d+).*?(?:на|to)\s*([\d.,]+(?:\s*[kкк])?)', cmd, re.IGNORECASE)
        )
        
        if match_price:
            try:
                orig_line = match_price.group(1)
                line = int(orig_line) - 1
                
                # Get price value with k/к suffix handling
                price_val = match_price.group(2).lower().strip()
                has_k = 'k' in price_val or 'к' in price_val
                price_val = price_val.replace('k', '').replace('к', '')
                
                # Convert price to number
                try:
                    price = float(price_val.replace(',', '.'))
                    if has_k:
                        price *= 1000
                except ValueError:
                    results.append({"action": "unknown", "error": "invalid_price_value"})
                    continue
                
                # Check if line index is valid
                if int(orig_line) < 1:
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": 0})
                elif invoice_lines is not None and (line < 0 or line >= invoice_lines):
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": line})
                else:
                    results.append({"action": "set_price", "line": line, "price": price})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_line_or_price"})
            continue
        
        # --- Name ---
        match_name = (
            re.search(r'(?:строка|line|row)\s*(-?\d+)\s*(?:название|имя|name)\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'(?:изменить название в строке|change name in row)\s*(-?\d+).*?(?:на|to)\s*(.+)', cmd, re.IGNORECASE)
        )
        
        if match_name:
            try:
                orig_line = match_name.group(1)
                line = int(orig_line) - 1
                # Проверяем, что индекс строки положительный
                if int(orig_line) < 1 or (invoice_lines is not None and (line < 0 or line >= invoice_lines)):
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": int(orig_line) - 1})
                else:
                    name = match_name.group(2).strip()
                    results.append({"action": "set_name", "line": line, "name": name})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_line_or_name"})
            continue
        
        # --- Quantity ---
        match_qty = (
            re.search(r'(?:строка|line|row)\s*(-?\d+)\s*(?:количество|кол-во|qty)\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'(?:изменить количество в строке|change qty in row)\s*(-?\d+).*?(?:на|to)\s*(.+)', cmd, re.IGNORECASE)
        )
        
        if match_qty:
            try:
                orig_line = match_qty.group(1)
                line = int(orig_line) - 1
                # Проверяем, что индекс строки положительный
                if int(orig_line) < 1:
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": 0})
                elif invoice_lines is not None and (line < 0 or line >= invoice_lines):
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": line})
                else:
                    try:
                        qty_val = match_qty.group(2).strip()
                        has_k = 'k' in qty_val.lower() or 'к' in qty_val.lower()
                        qty_val = qty_val.lower().replace('k', '').replace('к', '')
                        
                        qty = float(qty_val.replace(',', '.'))
                        if has_k:
                            qty *= 1000
                            
                        results.append({"action": "set_qty", "line": line, "qty": qty})
                    except Exception:
                        results.append({"action": "unknown", "error": "invalid_line_or_qty"})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_line_or_qty"})
            continue
        
        # --- Unit ---
        match_unit = (
            re.search(r'(?:строка|line|row)\s*(-?\d+)\s*(?:единица|ед\.|unit)\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'(?:изменить единицу в строке|change unit in row)\s*(-?\d+).*?(?:на|to)\s*(.+)', cmd, re.IGNORECASE)
        )
        
        if match_unit:
            try:
                orig_line = match_unit.group(1)
                line = int(orig_line) - 1
                # Check that line index is valid
                if int(orig_line) < 1 or (invoice_lines is not None and (line < 0 or line >= invoice_lines)):
                    results.append({"action": "unknown", "error": "line_out_of_range", "line": int(orig_line) - 1})
                else:
                    unit = match_unit.group(2).strip()
                    results.append({"action": "set_unit", "line": line, "unit": unit})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_line_or_unit"})
            continue
    
    # If no commands were recognized and we have reserved keywords, return a special error
    if not results and has_reserved_keywords:
        results.append({"action": "unknown", "error": "no_pattern_match", "user_input": user_input})
    # If completely empty and no reserved keywords, return an empty list to let the assistant handle it
    
    return results

def parse_assistant_output(raw: str) -> List[EditCommand]:
    """
    Принимает JSON-строку от Assistant.
    Возвращает список EditCommand.
    Универсально поддерживает оба формата: actions[] и одиночный action.
    """
    logger.info("[parse_assistant_output] Начало разбора ассистент-ответа", extra={"data": {"raw": raw}})
    try:
        data = json.loads(raw)
        logger.info("[parse_assistant_output] JSON успешно разобран", extra={"data": {"parsed": data}})
    except Exception as e:
        logger.error("[parse_assistant_output] Ошибка JSON", extra={"data": {"error": str(e), "raw": raw}})
        return [EditCommand(action="clarification_needed", error=raw)]

    # Универсальная логика: actions[] или одиночный action
    # Проверка наличия 'actions' или 'action'
    if not isinstance(data, dict):
        logger.error("[parse_assistant_output] Данные не являются словарем", extra={"data": data})
        parse_action_monitor.record_error()
        return [EditCommand(action="clarification_needed", error=raw)]
    
    # Обработка массива actions
    if "actions" in data and isinstance(data["actions"], list) and len(data["actions"]) > 0:
        actions = data["actions"]
        logger.info("[parse_assistant_output] Обнаружен массив actions с %d элементами", len(actions))
    # Обработка одиночного action
    elif "action" in data:
        actions = [data]
        logger.info("[parse_assistant_output] Обнаружен одиночный action")
    else:
        logger.warning("Assistant output: ни 'action', ни 'actions' не найдено, требуется уточнение", extra={"data": data})
        parse_action_monitor.record_error()
        return [EditCommand(action="clarification_needed", error=raw)]

    if not isinstance(actions, list):
        logger.error("[parse_assistant_output] 'actions' не список", extra={"data": {"actions": actions}})
        return [EditCommand(action="clarification_needed", error=raw)]
    
    logger.debug("Assistant parsed actions: %s", actions)
    cmds = []
    
    for i, obj in enumerate(actions):
        if not isinstance(obj, dict):
            logger.error(f"[parse_assistant_output] Action не dict", extra={"data": {"index": i, "item": obj}})
            continue  # Пропускаем некорректный элемент, но продолжаем обработку
            
        if "action" not in obj:
            logger.error(f"[parse_assistant_output] Элемент {i} не содержит поле 'action'", extra={"data": {"item": obj}})
            continue  # Пропускаем элемент без action, но продолжаем обработку
            
        try:
            cmds.append(EditCommand(**obj))
            logger.info(f"[parse_assistant_output] Добавлена команда {obj.get('action')} из элемента {i}")
        except ValidationError as ve:
            logger.error(f"[parse_assistant_output] Validation error", extra={"data": {"index": i, "item": obj, "error": str(ve)}})
            # Продолжаем обработку остальных элементов
        except ValueError as ve:
            logger.error(f"[parse_assistant_output] Validation error (row check)", extra={"data": {"index": i, "item": obj, "error": str(ve)}})
            # Продолжаем обработку остальных элементов
    
    # Если не удалось получить ни одной команды, возвращаем ошибку
    if not cmds:
        parse_action_monitor.record_error()
        return [EditCommand(action="clarification_needed", error="No valid commands could be extracted")]
        
    return cmds

logger = logging.getLogger(__name__)

# Инициализация OpenAI API клиента
client = openai.OpenAI(api_key=os.getenv("OPENAI_CHAT_KEY", getattr(settings, "OPENAI_CHAT_KEY", "")))

# Уменьшаем уровень логирования для избыточных логов
def optimize_logging():
    """
    Оптимизирует уровень логирования для различных модулей,
    чтобы уменьшить количество логов в production окружении.
    Это помогает улучшить производительность и снизить нагрузку на диск.
    """
    # HTTP клиенты (отключаем отладочные логи)
    for module in ["httpx", "httpcore", "httpcore.http11", "httpcore.connection"]:
        logger = logging.getLogger(module)
        logger.setLevel(logging.WARNING)
    
    # Установка более строгого уровня логирования для аутентификации
    # и обычных сообщений о статусе запросов
    auth_logger = logging.getLogger("openai.auth")
    if auth_logger:
        auth_logger.setLevel(logging.ERROR)
    
    # Отключаем ненужные дебаг логи от aiogram в production
    aiogram_logger = logging.getLogger("aiogram")
    if aiogram_logger:
        aiogram_logger.setLevel(logging.INFO)
    
    # Снижаем уровень детализации в openai API
    openai_logger = logging.getLogger("openai")
    if openai_logger:
        openai_logger.setLevel(logging.WARNING)
        
# Применяем настройки логирования при импорте модуля
optimize_logging()

# ID ассистента для обработки команд редактирования
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID", getattr(settings, "OPENAI_ASSISTANT_ID", ""))

# Хелпер для запуска асинхронного кода в синхронной функции
def run_async(func):
    """
    Декоратор для запуска асинхронных функций в синхронном контексте.
    Полезно для обратной совместимости.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

async def retry_openai_call(func, *args, max_retries=3, initial_backoff=1.0, **kwargs):
    """
    Helper function to retry OpenAI API calls with exponential backoff.
    
    Args:
        func: The OpenAI API function to call
        args: Positional arguments for the function
        max_retries: Maximum number of retries
        initial_backoff: Initial backoff time in seconds
        kwargs: Keyword arguments for the function
        
    Returns:
        The result of the API call
        
    Raises:
        Exception: If all retries fail
    """
    retries = 0
    last_error = None
    
    while retries <= max_retries:
        try:
            # Attempt to call the function
            return await asyncio.to_thread(func, *args, **kwargs)
            
        except (openai.RateLimitError, openai.APIError) as e:
            # These are the errors we want to retry with backoff
            last_error = e
            retries += 1
            if retries <= max_retries:
                # Exponential backoff
                backoff = initial_backoff * (2 ** (retries - 1))
                # Add jitter to avoid thundering herd problem
                jitter = 0.1 * backoff * (2 * asyncio.get_event_loop().time() % 1)
                total_backoff = backoff + jitter
                
                logger.warning(
                    f"OpenAI API error: {type(e).__name__}. "
                    f"Retrying in {total_backoff:.2f}s ({retries}/{max_retries})"
                )
                await asyncio.sleep(total_backoff)
            else:
                # We've exhausted our retries
                logger.error(f"OpenAI API error after {max_retries} retries: {e}")
                raise
                
        except Exception as e:
            # For other errors, don't retry
            logger.error(f"Non-retryable OpenAI API error: {type(e).__name__}: {e}")
            raise
    
    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected error in retry logic")


@trace_openai
async def run_thread_safe_async(user_input: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Асинхронная версия безопасного запуска OpenAI Thread с обработкой ошибок и таймаутом.
    Использует пул предварительно созданных thread для ускорения работы.
    
    Args:
        user_input: Текстовая команда пользователя
        timeout: Максимальное время ожидания в секундах
    
    Returns:
        Dict: JSON-объект с результатом разбора команды
    """
    start_time = time.time()
    latency = None
    thread_id = None
    run_id = None
    
    try:
        # Кешируем thread_id по user_input (на 5 минут)
        thread_key = f"openai:thread:{hash(user_input)}"
        thread_id = cache_get(thread_key)
        if not thread_id:
            # Получаем thread из пула или создаем новый
            thread_id = await get_thread(client)
            cache_set(thread_key, thread_id, ex=300)
            logger.info(f"[run_thread_safe_async] Using thread from pool: {thread_id}")
        else:
            logger.info(f"[run_thread_safe_async] Using cached thread: {thread_id}")
        
        # Кешируем assistant_id (на 5 минут)
        assistant_key = "openai:assistant_id"
        cached_assistant_id = cache_get(assistant_key)
        if not cached_assistant_id:
            cache_set(assistant_key, ASSISTANT_ID, ex=300)
            cached_assistant_id = ASSISTANT_ID
            logger.info(f"[run_thread_safe_async] Using assistant ID: {cached_assistant_id}")

        # Добавляем сообщение пользователя с повторными попытками при ошибках API
        logger.info(f"[run_thread_safe_async] Adding user message: '{user_input}'")
        try:
            message = await retry_openai_call(
                client.beta.threads.messages.create,
                thread_id=thread_id,
                role="user",
                content=user_input,
                max_retries=2,
                initial_backoff=1.0
            )
        except Exception as e:
            logger.error(f"[run_thread_safe_async] Failed to add user message after retries: {e}")
            return {
                "action": "unknown", 
                "error": f"message_create_failed: {type(e).__name__}",
                "user_message": "Не удалось отправить сообщение. Пожалуйста, попробуйте позже."
            }

        # Запускаем ассистента с повторными попытками
        logger.info(f"[run_thread_safe_async] Creating run with assistant ID: {cached_assistant_id}")
        try:
            run = await retry_openai_call(
                client.beta.threads.runs.create,
                thread_id=thread_id,
                assistant_id=cached_assistant_id,
                max_retries=2,
                initial_backoff=1.0
            )
            run_id = run.id
        except Exception as e:
            logger.error(f"[run_thread_safe_async] Failed to create run after retries: {e}")
            return {
                "action": "unknown", 
                "error": f"run_create_failed: {type(e).__name__}",
                "user_message": "Не удалось создать сессию ассистента. Пожалуйста, попробуйте позже."
            }
        
        # Измеряем и логируем латенцию для создания запроса
        latency = time.time() - start_time
        from app.utils.monitor import latency_monitor
        latency_monitor.record_latency(latency * 1000)
        logger.info(f"assistant_latency_ms={int(latency*1000)}")
        if latency > 10:
            logger.warning(f"[LATENCY] OpenAI response time: {latency:.2f} sec (slow)", extra={"latency": latency})
        else:
            logger.info(f"[LATENCY] OpenAI response time: {latency:.2f} sec", extra={"latency": latency})
        
        # Ожидаем завершения с таймаутом и обработкой ошибок
        logger.info(f"[run_thread_safe_async] Waiting for run completion, run ID: {run.id}")
        poll_interval = 1.0  # Start with 1 second poll interval
        poll_count = 0
        
        while run.status in ["queued", "in_progress"]:
            if time.time() - start_time > timeout:
                logger.error(f"[run_thread_safe_async] Timeout waiting for Assistant API response after {timeout}s")
                
                # Try to cancel the run before returning
                try:
                    await retry_openai_call(
                        client.beta.threads.runs.cancel,
                        thread_id=thread_id,
                        run_id=run.id,
                        max_retries=1
                    )
                    logger.info(f"[run_thread_safe_async] Successfully cancelled run {run.id} after timeout")
                except Exception as cancel_err:
                    logger.warning(f"[run_thread_safe_async] Failed to cancel run after timeout: {cancel_err}")
                
                return {"action": "unknown", "error": "timeout", "user_message": "OpenAI response timed out. Please try again."}
            
            # Use dynamic polling with exponential backoff
            poll_count += 1
            if poll_count > 5:  # After 5 polls, increase interval to reduce API load
                poll_interval = min(5.0, poll_interval * 1.5)  # Cap at 5 seconds
            
            # Используем асинхронную задержку
            await asyncio.sleep(poll_interval)
            
            # Retrieve run status with retry logic
            try:
                run = await retry_openai_call(
                    client.beta.threads.runs.retrieve,
                    thread_id=thread_id,
                    run_id=run.id,
                    max_retries=2
                )
            except Exception as e:
                logger.error(f"[run_thread_safe_async] Failed to retrieve run status after retries: {e}")
                # Decide whether to continue polling or fail fast based on error type
                if isinstance(e, openai.RateLimitError):
                    # For rate limits, wait longer but keep trying
                    await asyncio.sleep(5.0)
                    continue
                else:
                    # For other errors, fail fast
                    return {
                        "action": "unknown", 
                        "error": f"run_retrieve_failed: {type(e).__name__}",
                        "user_message": "Произошла ошибка при ожидании ответа. Пожалуйста, попробуйте позже."
                    }
            
            logger.debug(f"[run_thread_safe_async] Current run status: {run.status}")
        
        # Обрабатываем результат
        if run.status == "requires_action":
            # Обработка случая, когда ассистент хочет вызвать функцию
            logger.info(f"[run_thread_safe_async] Run requires action, providing tool outputs")
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            
            for tool_call in tool_calls:
                # Здесь можно добавить обработку разных функций по их именам
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                logger.info(f"[run_thread_safe_async] Tool call: {function_name} with args: {function_args}")
                
                if function_name == "parse_edit_command":
                    results = parse_edit_command(function_args.get("command", ""), function_args.get("invoice_lines"))
                    tool_outputs.append({"tool_call_id": tool_call.id, "output": json.dumps(results, ensure_ascii=False)})
                    logger.info(f"[run_thread_safe_async] parse_edit_command result: {results}")
                    continue
                else:
                    # Для неизвестных функций возвращаем ошибку
                    logger.warning(f"[run_thread_safe_async] Unsupported function: {function_name}")
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps({"action": "unknown", "error": "unsupported_function"})
                    })
            
            # Отправляем результаты выполнения функций обратно ассистенту с retry
            logger.info(f"[run_thread_safe_async] Submitting tool outputs")
            try:
                run = await retry_openai_call(
                    client.beta.threads.runs.submit_tool_outputs,
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                    max_retries=2
                )
            except Exception as e:
                logger.error(f"[run_thread_safe_async] Failed to submit tool outputs after retries: {e}")
                return {
                    "action": "unknown", 
                    "error": f"tool_submit_failed: {type(e).__name__}",
                    "user_message": "Произошла ошибка при обработке инструментов. Пожалуйста, попробуйте еще раз."
                }
            
            # Ждем завершения после отправки результатов функций - с той же логикой повторных попыток
            logger.info(f"[run_thread_safe_async] Waiting for run completion after tool outputs")
            poll_interval = 1.0
            poll_count = 0
            
            while run.status in ["queued", "in_progress"]:
                if time.time() - start_time > timeout:
                    logger.error(f"[run_thread_safe_async] Timeout waiting for Assistant API response after tool outputs, {timeout}s")
                    # Try to cancel before returning
                    try:
                        await retry_openai_call(
                            client.beta.threads.runs.cancel,
                            thread_id=thread_id,
                            run_id=run.id,
                            max_retries=1
                        )
                    except Exception:
                        pass  # Ignore cancel errors at this point
                    
                    return {"action": "unknown", "error": "timeout_after_tools", "user_message": "OpenAI response timed out after tool execution. Please try again."}
                
                # Dynamic polling interval
                poll_count += 1
                if poll_count > 5:
                    poll_interval = min(5.0, poll_interval * 1.5)
                
                await asyncio.sleep(poll_interval)
                
                try:
                    run = await retry_openai_call(
                        client.beta.threads.runs.retrieve,
                        thread_id=thread_id,
                        run_id=run.id,
                        max_retries=2
                    )
                except Exception as e:
                    if isinstance(e, openai.RateLimitError):
                        # For rate limits, wait longer but keep trying
                        await asyncio.sleep(5.0)
                        continue
                    else:
                        logger.error(f"[run_thread_safe_async] Failed to retrieve run status after tool outputs: {e}")
                        return {
                            "action": "unknown", 
                            "error": f"run_retrieve_failed_after_tools: {type(e).__name__}",
                            "user_message": "Произошла ошибка при ожидании ответа. Пожалуйста, попробуйте позже."
                        }
                
                logger.debug(f"[run_thread_safe_async] Current run status after tool outputs: {run.status}")
            
            # Проверяем статус после отправки результатов функций
            if run.status == "requires_action":
                # Если ассистент снова запрашивает функции, пробуем извлечь команду из запроса пользователя
                logger.info("[run_thread_safe_async] Assistant requires more actions, attempting to extract command from user input")
                
                # Используем наш адаптер для извлечения команды из исходного запроса
                extracted_intent = adapt_intent(user_input)
                if extracted_intent.get("action") != "unknown":
                    logger.info(f"[run_thread_safe_async] Successfully extracted intent from user input: {extracted_intent}")
                    return extracted_intent
                
                # Если не удалось извлечь команду, возвращаем ошибку
                logger.error("[run_thread_safe_async] Failed to extract command from user input")
                return {
                    "action": "unknown", 
                    "error": "multiple_tool_requests", 
                    "user_message": "Could not process your command. Please try to formulate your request more clearly."
                }
            elif run.status != "completed":
                # Check for specific failed statuses that might need different handling
                if run.status == "failed" and hasattr(run, "last_error"):
                    error_code = getattr(run.last_error, "code", "unknown")
                    error_message = getattr(run.last_error, "message", "Unknown error")
                    logger.error(f"[run_thread_safe_async] Run failed with error code {error_code}: {error_message}")
                    
                    # Special handling for rate limits or system errors
                    if error_code in ["rate_limit_exceeded", "server_error"]:
                        return {
                            "action": "unknown", 
                            "error": f"openai_error:{error_code}", 
                            "user_message": "OpenAI сервис временно недоступен. Пожалуйста, попробуйте позже."
                        }
                
                logger.error(f"[run_thread_safe_async] Run failed after tool outputs with status: {run.status}")
                return {
                    "action": "unknown", 
                    "error": f"run_failed_after_tools: {run.status}",
                    "user_message": "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз."
                }
                
        if run.status == "completed":
            # Получаем последнее сообщение ассистента с retry
            logger.info(f"[run_thread_safe_async] Run completed, retrieving assistant messages")
            try:
                messages = await retry_openai_call(
                    client.beta.threads.messages.list,
                    thread_id=thread_id,
                    max_retries=2
                )
            except Exception as e:
                logger.error(f"[run_thread_safe_async] Failed to retrieve messages after retries: {e}")
                return {
                    "action": "unknown", 
                    "error": f"messages_retrieve_failed: {type(e).__name__}",
                    "user_message": "Не удалось получить ответ ассистента. Пожалуйста, попробуйте позже."
                }
            
            # Находим последнее сообщение от ассистента
            assistant_messages = [
                msg for msg in messages.data 
                if msg.role == "assistant"
            ]
            
            if not assistant_messages:
                logger.error("[run_thread_safe_async] Assistant did not generate any response")
                return {
                    "action": "unknown", 
                    "error": "no_response",
                    "user_message": "Ассистент не сгенерировал ответ. Пожалуйста, попробуйте еще раз."
                }
            
            # Извлекаем ответ из сообщения
            try:
                content = assistant_messages[0].content[0].text.value
                logger.info(f"[run_thread_safe_async] Assistant response received ({len(content)} chars)")
                
                # Используем наш адаптер для обработки ответа
                result = adapt_intent(content)
                
                # Логируем результат адаптации
                logger.info(f"[run_thread_safe_async] Adapted intent: {result}")
                
                # Если адаптер вернул ошибку, но есть user_message для отображения, возвращаем его
                if result.get("action") == "unknown" and "user_message" not in result:
                    result["user_message"] = "Не удалось распознать команду. Пожалуйста, попробуйте сформулировать запрос четче."
                
                # Лог успешного завершения
                elapsed = time.time() - start_time
                logger.info(f"[run_thread_safe_async] Assistant run ok in {elapsed:.1f} s, action={result.get('action')}")
                return result
                
            except Exception as e:
                logger.exception(f"[run_thread_safe_async] Error parsing assistant response: {e}")
                return {
                    "action": "unknown", 
                    "error": f"parse_error: {str(e)}",
                    "user_message": "Произошла ошибка при разборе ответа ассистента. Пожалуйста, попробуйте еще раз."
                }
        else:
            # Обрабатываем неуспешные статусы
            # Check for specific error codes if available
            error_msg = "Unknown error"
            if hasattr(run, "last_error") and run.last_error:
                error_code = getattr(run.last_error, "code", "unknown")
                error_msg = getattr(run.last_error, "message", "Unknown error")
                logger.error(f"[run_thread_safe_async] Run failed with error code {error_code}: {error_msg}")
            
            logger.error(f"[run_thread_safe_async] Run failed with status: {run.status}, message: {error_msg}")
            return {
                "action": "unknown", 
                "error": f"run_failed: {run.status}",
                "user_message": "OpenAI request failed. Please try again later."
            }
            
    except openai.RateLimitError as e:
        # Ошибка лимита запросов
        logger.exception(f"[run_thread_safe_async] OpenAI rate limit error: {e}")
        
        # Try to cancel any active run before returning
        if thread_id and run_id:
            try:
                await asyncio.to_thread(
                    client.beta.threads.runs.cancel,
                    thread_id=thread_id,
                    run_id=run_id
                )
            except Exception:
                pass  # Ignore cancel errors
        
        return {
            "action": "unknown", 
            "error": "rate_limit_error",
            "user_message": "OpenAI rate limit exceeded. Please try again in a few moments."
        }
    except openai.APIConnectionError as e:
        # Ошибка соединения с API
        logger.exception(f"[run_thread_safe_async] OpenAI API connection error: {e}")
        return {
            "action": "unknown", 
            "error": "api_connection_error",
            "user_message": "OpenAI connection error. Please check your internet connection."
        }
    except openai.AuthenticationError as e:
        # Ошибка аутентификации
        logger.exception(f"[run_thread_safe_async] OpenAI authentication error: {e}")
        return {
            "action": "unknown", 
            "error": "authentication_error",
            "user_message": "OpenAI authentication error. Please contact your administrator."
        }
    except Exception as e:
        # Общая обработка ошибок
        logger.exception(f"[run_thread_safe_async] Error in OpenAI Assistant API call: {e}")
        
        # Try to cancel any active run before returning
        if thread_id and run_id:
            try:
                await asyncio.to_thread(
                    client.beta.threads.runs.cancel,
                    thread_id=thread_id,
                    run_id=run_id
                )
            except Exception:
                pass  # Ignore cancel errors
        
        return {
            "action": "unknown", 
            "error": str(e),
            "user_message": "An error occurred while processing your request. Please try again."
        }


@trace_openai
def run_thread_safe(user_input: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Безопасный запуск OpenAI Thread с обработкой ошибок и таймаутом.
    Синхронная обертка вокруг асинхронной функции для обратной совместимости.
    
    Args:
        user_input: Текстовая команда пользователя
        timeout: Максимальное время ожидания в секундах
    
    Returns:
        Dict: JSON-объект с результатом разбора команды
    """
    # Используем синхронную обертку для асинхронной функции
    return asyncio.run(run_thread_safe_async(user_input, timeout))