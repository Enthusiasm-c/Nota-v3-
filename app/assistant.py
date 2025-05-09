import time
from openai import OpenAI
from app.config import settings

_client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)


def ask_assistant(thread_id: str, user_message: str) -> str:
    """Шлём запрос ассистенту и ждём финального ответа (blocking)."""
    _client.beta.threads.messages.create(thread_id, role="user", content=user_message)
    run = _client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=settings.OPENAI_ASSISTANT_ID
    )
    # опрос статуса
    while True:
        run = _client.beta.threads.runs.retrieve(thread_id, run.id)
        if run.status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    msgs = _client.beta.threads.messages.list(thread_id)
    return msgs.data[0].content[0].text.value
