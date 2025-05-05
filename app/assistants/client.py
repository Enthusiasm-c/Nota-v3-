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