"""
Вспомогательные функции для работы с OpenAI API.

Этот модуль содержит утилиты для безопасного взаимодействия с OpenAI API,
с обработкой ошибок и поддержкой как реальных, так и имитирующих клиентов.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def is_dummy_client(client: Any) -> bool:
    """
    Проверяет, является ли клиент имитирующим (DummyClient).

    Args:
        client: Клиент OpenAI

    Returns:
        True, если клиент имитирующий, False в противном случае
    """
    if client is None:
        return True

    # Проверяем по имени класса
    client_type = client.__class__.__name__
    return "dummy" in client_type.lower() or "mock" in client_type.lower()


def safe_openai_chat_completion(
    client: Any,
    messages: List[Dict[str, str]],
    model: str = "gpt-4o",
    temperature: float = 0.2,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    fail_silently: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Безопасно вызывает OpenAI API с обработкой ошибок и повторными попытками.

    Работает как с реальным клиентом OpenAI, так и с имитирующим (DummyClient).

    Args:
        client: Клиент OpenAI
        messages: Список сообщений для API
        model: Модель OpenAI для использования
        temperature: Температура для генерации
        max_retries: Максимальное количество повторных попыток
        retry_delay: Задержка между повторными попытками в секундах
        fail_silently: Если True, вернет None вместо вызова исключения

    Returns:
        Ответ от API или None, если fail_silently=True и произошла ошибка
    """
    if client is None:
        logger.warning("OpenAI client is None, returning dummy response")
        return _get_dummy_response(messages)

    # Проверяем, является ли клиент имитирующим
    if is_dummy_client(client):
        logger.info("Using dummy OpenAI client")
        return _get_dummy_response(messages)

    # Проверяем наличие метода chat у клиента
    if not hasattr(client, "chat"):
        logger.warning("OpenAI client has no chat attribute, using dummy response")
        return _get_dummy_response(messages)

    # Выполняем запрос с повторными попытками
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
            return {
                "choices": [
                    {
                        "message": {
                            "content": response.choices[0].message.content,
                            "role": response.choices[0].message.role,
                        }
                    }
                ]
            }
        except Exception as e:
            logger.error(f"OpenAI API error (attempt {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Экспоненциальная задержка
            elif not fail_silently:
                raise

    # Если все попытки не удались и fail_silently=True
    logger.warning("All OpenAI API attempts failed, returning dummy response")
    return _get_dummy_response(messages)


def _get_dummy_response(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Создает имитацию ответа от OpenAI API для тестирования.

    Args:
        messages: Список сообщений, отправленных в API

    Returns:
        Имитация ответа от API
    """
    # Извлекаем последнее сообщение пользователя
    last_user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_message = msg.get("content", "")
            break

    # Генерируем простой ответ
    if last_user_message:
        dummy_response = f"Это тестовый ответ на запрос: '{last_user_message[:50]}...'"
    else:
        dummy_response = "Это тестовый ответ от имитации OpenAI API."

    return {"choices": [{"message": {"content": dummy_response, "role": "assistant"}}]}


def process_cell_with_gpt4o(
    client: Any, cell_text: str, prompt_template: str, context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Обрабатывает текстовую ячейку с помощью OpenAI API.

    Args:
        client: Клиент OpenAI
        cell_text: Текст ячейки для обработки
        prompt_template: Шаблон запроса
        context: Дополнительный контекст для шаблона

    Returns:
        Обработанный текст
    """
    if not cell_text.strip():
        return ""

    # Формируем сообщения для API
    ctx = context or {}
    full_prompt = prompt_template.format(cell_text=cell_text, **ctx)

    messages = [
        {"role": "system", "content": "Вы точный экстрактор текста из ячеек таблиц."},
        {"role": "user", "content": full_prompt},
    ]

    try:
        # Используем безопасную функцию вызова API
        response = safe_openai_chat_completion(
            client=client, messages=messages, model="gpt-4o", temperature=0.1, fail_silently=True
        )

        if response and "choices" in response and response["choices"]:
            return response["choices"][0]["message"]["content"].strip()

        logger.warning(f"Empty or invalid response from OpenAI API for cell: {cell_text[:50]}")
        return cell_text

    except Exception as e:
        logger.error(f"Error processing cell with GPT-4o: {str(e)}")
        return cell_text
