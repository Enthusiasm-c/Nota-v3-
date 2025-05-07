import logging
import time
from unittest.mock import patch, MagicMock
from app.assistants import client as assistant_client

def test_latency_logging_info_and_warning(caplog):
    # Мокаем OpenAI client и Redis
    with patch.object(assistant_client, 'client') as mock_client, \
         patch('app.utils.redis_cache.cache_get', return_value=None), \
         patch('app.utils.redis_cache.cache_set'):

        # Мокаем создание thread, message, run
        mock_thread = MagicMock()
        mock_thread.id = 'thread-123'
        mock_client.beta.threads.create.return_value = mock_thread
        mock_message = MagicMock()
        mock_client.beta.threads.messages.create.return_value = mock_message
        mock_run = MagicMock()
        mock_run.status = 'completed'
        mock_client.beta.threads.runs.create.return_value = mock_run
        # simulate fast response
        caplog.set_level(logging.INFO)
        start = time.time()
        assistant_client.run_thread_safe('fast input', timeout=5)
        info_logs = [r for r in caplog.records if '[LATENCY]' in r.getMessage()]
        assert any('OpenAI response time' in r.getMessage() for r in info_logs)

        # simulate slow response
        with patch('time.time', side_effect=[start, start+11]):
            caplog.clear()
            assistant_client.run_thread_safe('slow input', timeout=5)
            warn_logs = [r for r in caplog.records if '[LATENCY]' in r.getMessage()]
            assert any('slow' in r.getMessage().lower() or 'warning' in r.getMessage().lower() for r in warn_logs)
