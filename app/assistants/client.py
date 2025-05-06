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
    Args:
        user_input: строка команды пользователя
        invoice_lines: (опционально) количество строк в инвойсе для проверки границ
    Returns:
        Список dict'ов с действиями
    """
    import re
    commands = [c.strip() for c in user_input.replace('\n', ';').split(';') if c.strip()]
    results = []
    for cmd in commands:
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
        # Исправленная обработка total: ловим ValueError, если число некорректно
        match_total = re.search(r'(общая сумма|итого|total)\s*([\d.,]+)', cmd, re.IGNORECASE)
        if match_total:
            try:
                val = match_total.group(2)
                # Проверяем, что только одно число (иначе ValueError)
                if val.count(',') > 1 or val.count('.') > 1:
                    raise ValueError('invalid number format')
                total = float(val.replace(',', '.'))
                results.append({"action": "set_total", "total": total})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_total_value"})
            continue
        # --- Name ---
        match_name = (
            re.search(r'строка\s*(-?\d+)\s*(?:название|имя)\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'row\s*(-?\d+)\s*name\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'изменить название в строке\s*(-?\d+) на (.+)', cmd, re.IGNORECASE) or
            re.search(r'change name in row\s*(-?\d+) to (.+)', cmd, re.IGNORECASE)
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
            re.search(r'строка\s*(-?\d+)\s*количество\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'row\s*(-?\d+)\s*qty\s*(.+)', cmd, re.IGNORECASE) or
            re.search(r'изменить количество в строке\s*(-?\d+) на (.+)', cmd, re.IGNORECASE) or
            re.search(r'change qty in row\s*(-?\d+) to (.+)', cmd, re.IGNORECASE)
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
                        qty = float(match_qty.group(2).replace(',', '.'))
                        results.append({"action": "set_qty", "line": line, "qty": qty})
                    except Exception:
                        results.append({"action": "unknown", "error": "invalid_line_or_qty"})
            except Exception:
                results.append({"action": "unknown", "error": "invalid_line_or_qty"})
            continue
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
        return [EditCommand(action="clarification_needed", error="Не удалось извлечь ни одну валидную команду")]
        
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

@trace_openai
async def run_thread_safe_async(user_input: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Асинхронная версия безопасного запуска OpenAI Thread с обработкой ошибок и таймаутом.
    
    Args:
        user_input: Текстовая команда пользователя
        timeout: Максимальное время ожидания в секундах
    
    Returns:
        Dict: JSON-объект с результатом разбора команды
    """
    start_time = time.time()
    latency = None
    try:
        # Кешируем thread_id по user_input (на 5 минут)
        thread_key = f"openai:thread:{hash(user_input)}"
        thread_id = cache_get(thread_key)
        if not thread_id:
            thread = client.beta.threads.create()
            thread_id = thread.id
            cache_set(thread_key, thread_id, ex=300)
            logger.info(f"[run_thread_safe_async] Created new thread: {thread_id}")
        else:
            logger.info(f"[run_thread_safe_async] Using cached thread: {thread_id}")
        
        # Кешируем assistant_id (на 5 минут)
        assistant_key = "openai:assistant_id"
        cached_assistant_id = cache_get(assistant_key)
        if not cached_assistant_id:
            cache_set(assistant_key, ASSISTANT_ID, ex=300)
            cached_assistant_id = ASSISTANT_ID
            logger.info(f"[run_thread_safe_async] Using assistant ID: {cached_assistant_id}")

        # Добавляем сообщение пользователя
        logger.info(f"[run_thread_safe_async] Adding user message: '{user_input}'")
        # Используем asyncio.to_thread для выполнения синхронных операций в отдельном потоке
        message = await asyncio.to_thread(
            client.beta.threads.messages.create,
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        # Запускаем ассистента (используем кэшированный id)
        logger.info(f"[run_thread_safe_async] Creating run with assistant ID: {cached_assistant_id}")
        run = await asyncio.to_thread(
            client.beta.threads.runs.create,
            thread_id=thread_id,
            assistant_id=cached_assistant_id
        )
        
        # Измеряем и логируем латенцию для создания запроса
        latency = time.time() - start_time
        from app.utils.monitor import latency_monitor
        latency_monitor.record_latency(latency * 1000)
        logger.info(f"assistant_latency_ms={int(latency*1000)}")
        if latency > 10:
            logger.warning(f"[LATENCY] OpenAI response time: {latency:.2f} sec (slow)", extra={"latency": latency})
        else:
            logger.info(f"[LATENCY] OpenAI response time: {latency:.2f} sec", extra={"latency": latency})
        
        # Ожидаем завершения с таймаутом
        logger.info(f"[run_thread_safe_async] Waiting for run completion, run ID: {run.id}")
        while run.status in ["queued", "in_progress"]:
            if time.time() - start_time > timeout:
                logger.error(f"[run_thread_safe_async] Timeout waiting for Assistant API response after {timeout}s")
                return {"action": "unknown", "error": "timeout", "user_message": "Превышено время ожидания ответа от OpenAI. Пожалуйста, попробуйте еще раз."}
            
            # Используем асинхронную задержку вместо блокирования потока
            await asyncio.sleep(1)
            run = await asyncio.to_thread(
                client.beta.threads.runs.retrieve,
                thread_id=thread_id,
                run_id=run.id
            )
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
            
            # Отправляем результаты выполнения функций обратно ассистенту
            logger.info(f"[run_thread_safe_async] Submitting tool outputs: {tool_outputs}")
            run = await asyncio.to_thread(
                client.beta.threads.runs.submit_tool_outputs,
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
            
            # Ждем завершения после отправки результатов функций
            logger.info(f"[run_thread_safe_async] Waiting for run completion after tool outputs")
            while run.status in ["queued", "in_progress"]:
                if time.time() - start_time > timeout:
                    logger.error(f"[run_thread_safe_async] Timeout waiting for Assistant API response after tool outputs, {timeout}s")
                    return {"action": "unknown", "error": "timeout_after_tools", "user_message": "Превышено время ожидания ответа от OpenAI после вызова инструментов. Пожалуйста, попробуйте еще раз."}
                
                # Используем асинхронную задержку вместо блокирования потока
                await asyncio.sleep(1)
                run = await asyncio.to_thread(
                    client.beta.threads.runs.retrieve,
                    thread_id=thread_id,
                    run_id=run.id
                )
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
                    "user_message": "Не удалось обработать вашу команду. Пожалуйста, попробуйте сформулировать запрос четче."
                }
            elif run.status != "completed":
                logger.error(f"[run_thread_safe_async] Run failed after tool outputs with status: {run.status}")
                return {
                    "action": "unknown", 
                    "error": f"run_failed_after_tools: {run.status}",
                    "user_message": "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз."
                }
                
        if run.status == "completed":
            # Получаем последнее сообщение ассистента
            logger.info(f"[run_thread_safe_async] Run completed, retrieving assistant messages")
            messages = await asyncio.to_thread(
                client.beta.threads.messages.list,
                thread_id=thread_id
            )
            
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
                logger.info(f"[run_thread_safe_async] Assistant response: '{content[:100]}...'")
                
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
            logger.error(f"[run_thread_safe_async] Run failed with status: {run.status}")
            return {
                "action": "unknown", 
                "error": f"run_failed: {run.status}",
                "user_message": "Запрос к OpenAI не выполнен. Пожалуйста, попробуйте еще раз позже."
            }
            
    except openai.RateLimitError as e:
        # Ошибка лимита запросов
        logger.exception(f"[run_thread_safe_async] OpenAI rate limit error: {e}")
        return {
            "action": "unknown", 
            "error": "rate_limit_error",
            "user_message": "Превышен лимит запросов к OpenAI. Пожалуйста, попробуйте позже."
        }
    except openai.APIConnectionError as e:
        # Ошибка соединения с API
        logger.exception(f"[run_thread_safe_async] OpenAI API connection error: {e}")
        return {
            "action": "unknown", 
            "error": "api_connection_error",
            "user_message": "Ошибка соединения с OpenAI. Пожалуйста, проверьте подключение к интернету."
        }
    except openai.AuthenticationError as e:
        # Ошибка аутентификации
        logger.exception(f"[run_thread_safe_async] OpenAI authentication error: {e}")
        return {
            "action": "unknown", 
            "error": "authentication_error",
            "user_message": "Ошибка аутентификации в OpenAI. Пожалуйста, обратитесь к администратору."
        }
    except Exception as e:
        # Общая обработка ошибок
        logger.exception(f"[run_thread_safe_async] Error in OpenAI Assistant API call: {e}")
        return {
            "action": "unknown", 
            "error": str(e),
            "user_message": "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз."
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