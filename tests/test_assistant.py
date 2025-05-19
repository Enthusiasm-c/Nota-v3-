from unittest.mock import MagicMock, patch
from app import assistant


def test_ask_assistant_success():
    thread_id = "thread-123"
    user_message = "Hello!"
    # Мокаем OpenAI клиента и settings
    with patch("app.assistant._client") as mock_client, \
         patch("app.config.settings.OPENAI_ASSISTANT_ID", "asst-xyz"):
        # Мокаем создание сообщения
        mock_client.beta.threads.messages.create.return_value = None
        # Мокаем создание run
        mock_run = MagicMock()
        mock_run.id = "run-1"
        mock_run.status = "completed"
        mock_client.beta.threads.runs.create.return_value = mock_run
        mock_client.beta.threads.runs.retrieve.return_value = mock_run
        # Мокаем список сообщений
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=MagicMock(value="Ответ ассистента"))]
        mock_msgs = MagicMock()
        mock_msgs.data = [mock_msg]
        mock_client.beta.threads.messages.list.return_value = mock_msgs

        result = assistant.ask_assistant(thread_id, user_message)
        assert result == "Ответ ассистента" 