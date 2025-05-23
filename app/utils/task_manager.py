import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Словарь для хранения активных задач
active_tasks: Dict[str, asyncio.Task] = {}


def register_task(task_id: str, task: asyncio.Task) -> None:
    """Регистрирует задачу в глобальном словаре."""
    active_tasks[task_id] = task


def cancel_task(task_id: str) -> bool:
    """Отменяет задачу по ID и возвращает True, если задача была отменена."""
    if task_id in active_tasks:
        task = active_tasks[task_id]
        if not task.done():
            task.cancel()
            logger.info(f"Task {task_id} cancelled")
            return True
        del active_tasks[task_id]
    return False


def cleanup_tasks() -> int:
    """Очищает завершённые задачи и возвращает количество очищенных."""
    to_delete = [tid for tid, task in active_tasks.items() if task.done()]
    for tid in to_delete:
        del active_tasks[tid]
    return len(to_delete)
