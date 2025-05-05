"""
OpenAI Assistant API клиент для Nota.
Предоставляет интерфейс для обработки текстовых команд через GPT-3.5-turbo.
"""

import json
import logging
import time
import re
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
    """
    start_time = time.time()
    
    try:
        # Создаем новый тред
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
                
                # Новый универсальный парсер команд для инвойса
                if function_name == "parse_edit_command":
                    command = function_args.get("command", "")
                    commands = [c.strip() for c in command.replace('\n', ';').split(';') if c.strip()]
                    invoice_lines = function_args.get("invoice_lines")
                    results = []
                    for cmd in commands:
                        # --- Supplier ---
                        if (cmd.lower().startswith("поставщик ") or
                            "изменить поставщика на" in cmd.lower() or
                            cmd.lower().startswith("supplier ") or
                            "change supplier to" in cmd.lower()):
                            # Сохраняем оригинальный регистр
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
                        match_total = re.search(r'(общая сумма|итого|total)\s*(\d+[.,]?\d*)', cmd, re.IGNORECASE)
                        if match_total:
                            try:
                                total = float(match_total.group(2).replace(',', '.'))
                                results.append({"action": "set_total", "total": total})
                            except Exception:
                                results.append({"action": "unknown", "error": "invalid_total_value"})
                            continue
                        # --- Name ---
                        match_name = (
                            re.search(r'строка\s*(\d+)\s*(?:название|имя)\s*(.+)', cmd, re.IGNORECASE) or
                            re.search(r'row\s*(\d+)\s*name\s*(.+)', cmd, re.IGNORECASE) or
                            re.search(r'изменить название в строке\s*(\d+) на (.+)', cmd, re.IGNORECASE) or
                            re.search(r'change name in row\s*(\d+) to (.+)', cmd, re.IGNORECASE)
                        )
                        if match_name:
                            try:
                                line = int(match_name.group(1)) - 1
                                if invoice_lines is not None and (line < 0 or line >= invoice_lines):
                                    results.append({"action": "unknown", "error": "line_out_of_range", "line": line + 1})
                                else:
                                    name = match_name.group(2).strip()
                                    results.append({"action": "set_name", "line": line, "name": name})
                            except Exception:
                                results.append({"action": "unknown", "error": "invalid_line_or_name"})
                            continue
                        # --- Quantity ---
                        match_qty = (
                            re.search(r'строка\s*(\d+)\s*количество\s*(\d+[.,]?\d*)', cmd, re.IGNORECASE) or
                            re.search(r'row\s*(\d+)\s*qty\s*(\d+[.,]?\d*)', cmd, re.IGNORECASE) or
                            re.search(r'изменить количество в строке\s*(\d+) на (\d+[.,]?\d*)', cmd, re.IGNORECASE) or
                            re.search(r'change qty in row\s*(\d+) to (\d+[.,]?\d*)', cmd, re.IGNORECASE)
                        )
                        if match_qty:
                            try:
                                line = int(match_qty.group(1)) - 1
                                if invoice_lines is not None and (line < 0 or line >= invoice_lines):
                                    results.append({"action": "unknown", "error": "line_out_of_range", "line": line + 1})
                                else:
                                    qty = float(match_qty.group(2).replace(',', '.'))
                                    results.append({"action": "set_qty", "line": line, "qty": qty})
                            except Exception:
                                results.append({"action": "unknown", "error": "invalid_line_or_qty"})
                            continue
                        # --- Unit ---
                        match_unit = (
                            re.search(r'строка\s*(\d+)\s*(?:ед. изм.|единица измерения)\s*([a-zA-Zа-яА-ЯёЁ]+)', cmd, re.IGNORECASE) or
                            re.search(r'row\s*(\d+)\s*unit\s*([a-zA-Zа-яА-ЯёЁ]+)', cmd, re.IGNORECASE)
                        )
                        if match_unit:
                            try:
                                line = int(match_unit.group(1)) - 1
                                if invoice_lines is not None and (line < 0 or line >= invoice_lines):
                                    results.append({"action": "unknown", "error": "line_out_of_range", "line": line + 1})
                                else:
                                    unit = match_unit.group(2).strip()
                                    results.append({"action": "set_unit", "line": line, "unit": unit})
                            except Exception:
                                results.append({"action": "unknown", "error": "invalid_line_or_unit"})
                            continue
                        # --- Date ---
                        if re.search(r'(дата|date)', cmd, re.IGNORECASE):
                            try:
                                words = cmd.split()
                                months = {
                                    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
                                    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
                                    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
                                    "январь": 1, "февраль": 2, "март": 3, "апрель": 4,
                                    "май": 5, "июнь": 6, "июль": 7, "август": 8,
                                    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
                                    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
                                }
                                day = None
                                month = None
                                year = None
                                for word in words:
                                    if word.isdigit() and 1 <= int(word) <= 31 and day is None:
                                        day = int(word)
                                    elif word.isdigit() and int(word) > 2000 and year is None:
                                        year = int(word)
                                for word in words:
                                    if word.lower() in months:
                                        month = months[word.lower()]
                                        break
                                if day and month:
                                    date_str = f"{day} {month}"
                                    if year:
                                        date_str += f" {year}"
                                    results.append({"action": "set_date", "date": date_str})
                                else:
                                    results.append({"action": "unknown", "error": "invalid_date_format"})
                            except Exception:
                                results.append({"action": "unknown", "error": "invalid_date_parse"})
                            continue
                        # --- Unknown ---
                        results.append({"action": "unknown", "error": "unparseable_command", "command": cmd})
                    # Итоговый возврат
                    if len(results) == 1:
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps(results[0])
                        })
                    else:
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps({"actions": results})
                        })
                    continue

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
            
            # Проверяем статус после отправки результатов функций
            if run.status == "requires_action":
                # Если ассистент снова запрашивает функции, обрабатываем их еще раз
                logger.info("Assistant requires more actions, returning simple success response")
                # Возвращаем простой успешный ответ для установки даты
                # Это упрощение, но оно должно работать для большинства случаев
                # Ищем дату в исходной команде пользователя
                words = user_input.lower().split()
                months = {
                    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, 
                    "мая": 5, "июня": 6, "июля": 7, "августа": 8, 
                    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
                    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, 
                    "май": 5, "июнь": 6, "июль": 7, "август": 8, 
                    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
                }
                
                day = None
                month = None
                
                # Ищем день (число)
                for word in words:
                    if word.isdigit() and 1 <= int(word) <= 31 and day is None:
                        day = int(word)
                
                # Ищем месяц (название)
                for word in words:
                    if word in months:
                        month = months[word]
                        break
                
                # Если нашли и день, и месяц
                if day and month:
                    return {"action": "set_date", "date": f"{day} {month}"}
                else:
                    # Если не нашли дату, возвращаем ошибку
                    logger.error("Could not extract date from user input")
                    return {"action": "unknown", "error": "date_not_found"}
            elif run.status != "completed":
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
            
            # Извлекаем ответ из сообщения
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
                    # Если нет JSON в ответе, пытаемся распарсить текстовый ответ
                    logger.info(f"Parsing text response: {content}")
                    
                    # Пытаемся распознать команды в тексте
                    content_lower = content.lower()
                    
                    # Распознаем команду изменения даты
                    if ("дат" in content_lower or "date" in content_lower) and ("изменить" in content_lower or "исправить" in content_lower):
                        # Ищем числа (день) и месяцы в тексте
                        words = content_lower.split()
                        months = {
                            "января": 1, "февраля": 2, "марта": 3, "апреля": 4, 
                            "мая": 5, "июня": 6, "июля": 7, "августа": 8, 
                            "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
                            "январь": 1, "февраль": 2, "март": 3, "апрель": 4, 
                            "май": 5, "июнь": 6, "июль": 7, "август": 8, 
                            "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
                        }
                        
                        day = None
                        month = None
                        year = None
                        
                        # Ищем день (число)
                        for word in words:
                            if word.isdigit() and 1 <= int(word) <= 31 and day is None:
                                day = int(word)
                            elif word.isdigit() and int(word) > 2000 and year is None:
                                year = int(word)
                        
                        # Ищем месяц (название)
                        for word in words:
                            if word in months:
                                month = months[word]
                                break
                        
                        # Если нашли и день, и месяц
                        if day and month:
                            date_str = f"{day} {month}"
                            if year:
                                date_str += f" {year}"
                                
                            return {"action": "set_date", "date": date_str}
                    
                    # Если не удалось распознать команду, возвращаем ошибку
                    logger.error(f"Could not parse text response: {content}")
                    return {"action": "unknown", "error": "unparseable_text_response"}
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