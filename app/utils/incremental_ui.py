"""
Утилита для инкрементального обновления интерфейса пользователя в Telegram.

Предоставляет удобный интерфейс для показа прогресса длительных операций,
с поддержкой анимированных индикаторов и обновлений статуса в реальном времени.
"""

import logging
import asyncio
import time
import random
from typing import Optional, Dict, Any, List, Union, Callable
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from app.bot_utils import edit_message_text_safe

logger = logging.getLogger(__name__)

# Темы спиннеров
SPINNER_THEMES = {
    "default": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "dots": ["⠋", "⠙", "⠚", "⠞", "⠖", "⠦", "⠴", "⠲", "⠳", "⠓"],
    "loading": ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"],
    "table": ["◰", "◳", "◲", "◱"],
    "boxes": ["◰", "◴", "◱", "◵", "◲", "◶", "◳", "◷"],
    "invoice": ["📄", "📃", "📑", "📜", "📋"],
    "counting": ["🔢", "🔡", "🔠", "🔤", "🔣"],
    "lines": ["-", "\\", "|", "/"],
}

class IncrementalUI:
    """
    Класс для инкрементального обновления интерфейса пользователя в Telegram.
    
    Позволяет показывать прогресс длительных операций, обновляя одно и то же сообщение,
    вместо отправки множества сообщений. Поддерживает анимированные индикаторы 
    и различные темы визуализации.
    
    Attributes:
        bot: Экземпляр бота Telegram
        chat_id: ID чата, в котором отображается сообщение
        message_id: ID сообщения, которое обновляется
        text: Текущий текст сообщения
        _spinner_task: Асинхронная задача для анимации спиннера
        _spinner_running: Флаг, указывающий, запущен ли спиннер
    """
    
    def __init__(self, bot, chat_id: int):
        """
        Инициализирует новый UI для инкрементальных обновлений.
        
        Args:
            bot: Экземпляр бота Telegram
            chat_id: ID чата для отправки сообщений
        """
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = None
        self.text = ""
        self._spinner_task = None
        self._spinner_running = False
        self._theme = "default"
        self._start_time = None
        
    async def start(self, initial_text: str = "Начинаю обработку...") -> None:
        """
        Начинает новую последовательность обновлений с начальным текстом.
        
        Args:
            initial_text: Начальный текст сообщения
        """
        self._start_time = time.time()
        self.text = initial_text
        try:
            message = await self.bot.send_message(self.chat_id, initial_text)
            self.message_id = message.message_id
            logger.debug(f"Started incremental UI with message_id={self.message_id}")
        except Exception as e:
            logger.error(f"Error starting incremental UI: {e}")
            # Создаем фиктивный message_id, если отправка не удалась
            self.message_id = 0
    
    async def update(self, text: str) -> None:
        """
        Обновляет текст сообщения.
        
        Args:
            text: Новый текст сообщения
        """
        if self.message_id is None:
            logger.warning("Attempting to update before starting UI")
            return
            
        self.text = text
        
        try:
            await self.bot.edit_message_text(
                text, 
                chat_id=self.chat_id,
                message_id=self.message_id
            )
            logger.debug(f"Updated UI message: {text[:30]}...")
        except Exception as e:
            logger.warning(f"Error updating UI message: {e}")
    
    async def append(self, new_text: str) -> None:
        """
        Добавляет новый текст к существующему сообщению.
        
        Args:
            new_text: Текст для добавления
        """
        self.text = f"{self.text}\n{new_text}"
        await self.update(self.text)
    
    async def complete(self, completion_text: Optional[str] = None, kb: Optional[InlineKeyboardMarkup] = None) -> None:
        """
        Завершает последовательность обновлений с опциональным итоговым текстом и клавиатурой.
        
        Args:
            completion_text: Финальный текст для отображения
            kb: Опциональная клавиатура для добавления к сообщению
        """
        # Останавливаем спиннер, если он запущен
        self.stop_spinner()
        
        # Вычисляем общее время выполнения
        elapsed = time.time() - self._start_time if self._start_time else 0
        elapsed_str = f" (за {elapsed:.1f} сек)" if elapsed > 0 else ""
        
        # Формируем финальный текст
        if completion_text:
            final_text = f"{self.text}\n{completion_text}{elapsed_str}"
        else:
            final_text = f"{self.text}\n✅ Готово{elapsed_str}"
        
        try:
            # Если есть клавиатура, используем ее
            if kb:
                await self.bot.edit_message_text(
                    final_text,
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    reply_markup=kb
                )
            else:
                await self.update(final_text)
        except Exception as e:
            logger.error(f"Error completing UI: {e}")
            # Пробуем альтернативный способ в случае ошибки
            try:
                await edit_message_text_safe(
                    bot=self.bot,
                    chat_id=self.chat_id,
                    msg_id=self.message_id,
                    text=final_text,
                    kb=kb
                )
            except Exception as e2:
                logger.error(f"Fallback edit also failed: {e2}")
    
    async def complete_with_keyboard(self, final_text: str, has_errors: bool = False, lang: str = "ru") -> None:
        """
        Завершает последовательность обновлений с добавлением стандартной клавиатуры в зависимости от наличия ошибок.
        
        Args:
            final_text: Финальный текст для отображения
            has_errors: Флаг наличия ошибок, влияет на отображение кнопки "Подтвердить"
            lang: Язык для интернационализации
        """
        from app.keyboards import build_main_kb
        
        # Добавляем подробное логирование для диагностики
        logger.info(f"complete_with_keyboard: создаем клавиатуру с has_errors={has_errors}")
        
        # Явно передаем has_errors в build_main_kb
        keyboard = build_main_kb(has_errors=has_errors, lang=lang)
        
        # Используем стандартный метод complete с явной передачей клавиатуры
        await self.complete(final_text, kb=keyboard)
        logger.info(f"UI completed with keyboard, has_errors={has_errors}")
    
    async def error(self, error_text: str, show_timing: bool = False) -> None:
        """
        Показывает сообщение об ошибке.
        
        Args:
            error_text: Текст ошибки для отображения
            show_timing: Показывать ли время выполнения
        """
        self.stop_spinner()
        
        # Вычисляем время только если нужно отображать
        elapsed_str = ""
        if show_timing and self._start_time:
            elapsed = time.time() - self._start_time
            elapsed_str = f" (через {elapsed:.1f} сек)"
            
        await self.update(f"{self.text}\n❌ {error_text}{elapsed_str}")
    
    def stop_spinner(self) -> None:
        """Останавливает анимацию спиннера, если она запущена."""
        if self._spinner_running and self._spinner_task:
            self._spinner_running = False
            if not self._spinner_task.done():
                self._spinner_task.cancel()
    
    async def start_spinner(self, show_text: bool = True, theme: str = "default") -> None:
        """
        Запускает анимированный спиннер, обновляя сообщение.
        
        Args:
            show_text: Показывать ли текст вместе со спиннером
            theme: Тема спиннера (default, dots, loading и т.д.)
        """
        # Останавливаем предыдущий спиннер, если он запущен
        self.stop_spinner()
        
        self._theme = theme
        frames = SPINNER_THEMES.get(theme, SPINNER_THEMES["default"])
        
        # Запускаем новую задачу для анимации
        self._spinner_running = True
        self._spinner_task = asyncio.create_task(
            self._animate_spinner(frames, show_text)
        )
    
    async def _animate_spinner(self, frames: List[str], show_text: bool) -> None:
        """
        Внутренний метод для анимации спиннера.
        
        Args:
            frames: Кадры анимации спиннера
            show_text: Показывать ли текст вместе со спиннером
        """
        i = 0
        try:
            while self._spinner_running:
                frame = frames[i % len(frames)]
                
                if show_text:
                    spinner_text = f"{frame} {self.text}"
                else:
                    # Добавляем спиннер к последней строке
                    lines = self.text.split('\n')
                    lines[-1] = f"{lines[-1]} {frame}"
                    spinner_text = '\n'.join(lines)
                
                try:
                    await self.bot.edit_message_text(
                        spinner_text,
                        chat_id=self.chat_id,
                        message_id=self.message_id
                    )
                except Exception as e:
                    logger.debug(f"Spinner update error (normal during rapid updates): {e}")
                
                i += 1
                await asyncio.sleep(0.3)  # Интервал обновления
        except asyncio.CancelledError:
            logger.debug("Spinner animation cancelled")
        except Exception as e:
            logger.error(f"Error in spinner animation: {e}")
            self._spinner_running = False

    @staticmethod
    async def with_progress(message: Message, initial_text: str, 
                          process_func: Callable, 
                          final_text: Optional[str] = None,
                          final_kb: Optional[InlineKeyboardMarkup] = None,
                          error_text: Optional[str] = None) -> Any:
        """
        Выполняет функцию с прогрессивным UI и возвращает результат.
        
        Args:
            message: Сообщение, из которого нужно взять chat_id и bot
            initial_text: Начальный текст индикатора
            process_func: Асинхронная функция, которая будет вызвана с ui в качестве аргумента
            final_text: Финальный текст при успехе
            final_kb: Финальная клавиатура при успехе
            error_text: Шаблон текста ошибки
            
        Returns:
            Результат функции process_func
        """
        ui = IncrementalUI(message.bot, message.chat.id)
        await ui.start(initial_text)
        
        try:
            result = await process_func(ui)
            
            if final_text:
                await ui.complete(final_text, final_kb)
            else:
                await ui.complete(kb=final_kb)
                
            return result
        except Exception as e:
            logger.error(f"Error in with_progress: {e}", exc_info=True)
            error_msg = error_text or f"Произошла ошибка: {str(e)}"
            await ui.error(error_msg)
            raise