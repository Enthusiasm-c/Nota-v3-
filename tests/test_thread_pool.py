import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.assistants import thread_pool
import asyncio

@pytest.mark.asyncio
async def test_initialize_pool_creates_new():
    client = MagicMock()
    client.beta.threads.create = MagicMock()
    client.beta.threads.create.id = "tid1"
    with patch("app.assistants.thread_pool.cache_get", return_value=None), \
         patch("app.assistants.thread_pool.cache_set") as mock_set, \
         patch("app.assistants.thread_pool.create_thread", new=AsyncMock(return_value="tid1")):
        result = await thread_pool.initialize_pool(client, size=1)
        assert result == ["tid1"]
        mock_set.assert_called()

@pytest.mark.asyncio
async def test_initialize_pool_uses_existing():
    with patch("app.assistants.thread_pool.cache_get", return_value="tid1,tid2"), \
         patch("app.assistants.thread_pool.cache_set") as mock_set, \
         patch("app.assistants.thread_pool.create_thread", new=AsyncMock(return_value="tid3")):
        client = MagicMock()
        result = await thread_pool.initialize_pool(client, size=2)
        assert result == ["tid1", "tid2"]
        mock_set.assert_not_called()  # не нужно обновлять пул

@pytest.mark.asyncio
async def test_get_thread_from_pool():
    with patch("app.assistants.thread_pool.cache_get", return_value="tid1,tid2"), \
         patch("app.assistants.thread_pool.cache_set") as mock_set, \
         patch("app.assistants.thread_pool.create_thread", new=AsyncMock(return_value="tid3")), \
         patch("app.assistants.thread_pool.asyncio.create_task") as mock_task:
        client = MagicMock()
        thread_id = await thread_pool.get_thread(client)
        assert thread_id in ("tid1", "tid2")
        mock_set.assert_called()
        mock_task.assert_called()

@pytest.mark.asyncio
async def test_get_thread_creates_new_if_empty():
    with patch("app.assistants.thread_pool.cache_get", return_value=None), \
         patch("app.assistants.thread_pool.create_thread", new=AsyncMock(return_value="tidX")):
        client = MagicMock()
        thread_id = await thread_pool.get_thread(client)
        assert thread_id == "tidX"

@pytest.mark.asyncio
async def test_refill_pool_adds_threads():
    with patch("app.assistants.thread_pool.cache_get", return_value="tid1"), \
         patch("app.assistants.thread_pool.cache_set") as mock_set, \
         patch("app.assistants.thread_pool.create_thread", new=AsyncMock(side_effect=["tid2", "tid3"])):
        client = MagicMock()
        await thread_pool.refill_pool(client, target_size=3)
        mock_set.assert_called()
        args, kwargs = mock_set.call_args
        assert "tid2" in args[1] and "tid3" in args[1]

def test_release_thread_adds_to_pool():
    with patch("app.assistants.thread_pool.cache_get", return_value="tid1,tid2"), \
         patch("app.assistants.thread_pool.cache_set") as mock_set:
        thread_pool.release_thread("tid3")
        mock_set.assert_called()
        args, kwargs = mock_set.call_args
        assert "tid3" in args[1] 