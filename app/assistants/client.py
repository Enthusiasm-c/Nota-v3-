"""
OpenAI Assistant API клиент для Nota.
Предоставляет интерфейс для обработки текстовых команд через GPT-3.5-turbo.
"""

import json
import logging
import time
from typing import Dict, Any, Optional
import os
import openai
from app.config import settings

logger = logging.getLogger(__name__)

# Инициализация OpenAI API клиента
client = openai.OpenAI(api_key=os.getenv("OPENAI_CHAT_KEY", getattr(settings, "OPENAI_CHAT_KEY", "")))

# ID ассистента для обработки команд редактирования
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID", getattr(settings, "OPENAI_ASSISTANT_ID", ""))

def run_thread_safe(user_input: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Безопасный запуск OpenAI Thread с обработкой ошибок и таймаутом.
    
    Args:
        user_input: Текстовая команда пользователя
        timeout: Максимальное время ожидания в секундах
    
    Returns:
        Dict: JSON-объект с результатом разбора команды
        
    Raises:
        TimeoutError: Если запрос выполняется дольше timeout
        ValueError: Если ответ не соответствует ожидаемому формату
    """
    if not ASSISTANT_ID:
        logger.error("OpenAI Assistant ID не настроен")
        return {"action": "unknown", "error": "assistant_not_configured"}
    
    start_time = time.time()
    
    # Лог входящего сообщения
    logger.info(f"FREE EDIT → {user_input}")
    
    try:
        # Создаем thread
        thread = client.beta.threads.create()
        
        # Добавляем сообщение пользователя
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )
        
        # Запускаем ассистента
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )
        
        # Ожидаем завершения с таймаутом
        while run.status in ["queued", "in_progress"]:
            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for Assistant API response after {timeout}s")
                return {"action": "unknown", "error": "timeout"}
            
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
        
        # Обрабатываем результат
        if run.status == "requires_action":
            # Обработка случая, когда ассистент хочет вызвать функцию
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            
            for tool_call in tool_calls:
                # Здесь можно добавить обработку разных функций по их именам
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                # Простая эмуляция функции parse_edit_command
                if function_name == "parse_edit_command":
                    command = function_args.get("command", "")
                    
                    # Простой парсер для команды изменения даты
                    if "дата" in command.lower() or "date" in command.lower():
                        date_parts = [part for part in command.split() if part.isdigit() or part in ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]]
                        if len(date_parts) >= 2:
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"action": "set_date", "date": " ".join(date_parts)})
                            })
                        else:
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"action": "unknown", "error": "invalid_date_format"})
                            })
                    # Простой парсер для команды изменения строки
                    elif "строка" in command.lower() or "line" in command.lower():
                        parts = command.lower().split()
                        try:
                            line_idx = parts.index("строка") + 1 if "строка" in parts else parts.index("line") + 1
                            if line_idx < len(parts) and parts[line_idx].isdigit():
                                line_num = int(parts[line_idx])
                                
                                if "цена" in parts or "price" in parts:
                                    price_idx = parts.index("цена") + 1 if "цена" in parts else parts.index("price") + 1
                                    if price_idx < len(parts) and parts[price_idx].isdigit():
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"action": "set_price", "line": line_num - 1, "price": float(parts[price_idx])})
                                        })
                                    else:
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"action": "unknown", "error": "invalid_price_format"})
                                        })
                                else:
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"action": "unknown", "error": "unsupported_field"})
                                    })
                            else:
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"action": "unknown", "error": "invalid_line_number"})
                                })
                        except (ValueError, IndexError):
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"action": "unknown", "error": "parse_error"})
                            })
                    else:
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps({"action": "unknown", "error": "unsupported_command"})
                        })
                else:
                    # Для неизвестных функций возвращаем ошибку
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps({"action": "unknown", "error": "unsupported_function"})
                    })
            
            # Отправляем результаты выполнения функций обратно ассистенту
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
            
            # Ждем завершения после отправки результатов функций
            while run.status in ["queued", "in_progress"]:
                if time.time() - start_time > timeout:
                    logger.error(f"Timeout waiting for Assistant API response after tool outputs, {timeout}s")
                    return {"action": "unknown", "error": "timeout_after_tools"}
                
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            # Если после отправки результатов функций ассистент завершился успешно,
            # продолжаем обработку как обычно
            if run.status != "completed":
                logger.error(f"Assistant run failed after tool outputs with status: {run.status}")
                return {"action": "unknown", "error": f"run_failed_after_tools: {run.status}"}
                
        if run.status == "completed":
            # Получаем последнее сообщение ассистента
            messages = client.beta.threads.messages.list(
                thread_id=thread.id
            )
            
            # Находим последнее сообщение от ассистента
            assistant_messages = [
                msg for msg in messages.data 
                if msg.role == "assistant"
            ]
            
            if not assistant_messages:
                logger.error("Assistant did not generate any response")
                return {"action": "unknown", "error": "no_response"}
            
            # Извлекаем JSON-ответ из сообщения
            try:
                content = assistant_messages[0].content[0].text.value
                # Проверяем, есть ли JSON в тексте
                if "{" in content and "}" in content:
                    # Извлекаем только JSON-часть ответа
                    json_start = content.find("{")
                    json_end = content.rfind("}") + 1
                    json_str = content[json_start:json_end]
                    result = json.loads(json_str)
                    
                    # Проверка необходимых полей
                    if "action" not in result:
                        raise ValueError("Missing 'action' field in response")
                    
                    # Лог успешного завершения
                    elapsed = time.time() - start_time
                    logger.info(f"Assistant run ok in {elapsed:.1f} s")
                    
                    return result
                else:
                    # Если нет JSON в ответе, рассматриваем как ошибку
                    logger.error(f"Assistant response does not contain JSON: {content}")
                    return {"action": "unknown", "error": "no_json_in_response"}
            except Exception as e:
                logger.exception(f"Error parsing assistant response: {e}")
                return {"action": "unknown", "error": f"parse_error: {str(e)}"}
        else:
            # Обрабатываем неуспешные статусы
            logger.error(f"Assistant run failed with status: {run.status}")
            return {"action": "unknown", "error": f"run_failed: {run.status}"}
            
    except Exception as e:
        # Общая обработка ошибок
        logger.exception(f"Error in OpenAI Assistant API call: {e}")
        return {"action": "unknown", "error": str(e)}