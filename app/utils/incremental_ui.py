"""
IncrementalUI - класс для обеспечения прогрессивных обновлений UI в Telegram-боте.

Позволяет обновлять текст сообщений с индикаторами прогресса и новой информацией
во время обработки длительных операций.
"""

import logging
import asyncio
import time
from typing import Optional, Dict, Any, List, Union, Callable
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from app.bot_utils import edit_message_text_safe

logger = logging.getLogger("nota.incremental_ui")

class IncrementalUI:
    """
    Класс для управления прогрессивными обновлениями UI в Telegram-боте.
    
    Предоставляет методы для:
    - Создания сообщения с индикатором загрузки
    - Обновления сообщения с прогрессом
    - Завершения обновления UI с финальным сообщением
    
    Пример использования:
    ```python
    # Создание
    ui = IncrementalUI(message.bot, message.chat.id)
    msg = await ui.start("Начинаю обработку...")
    
    # Обновление в процессе выполнения
    await ui.update("Обработка OCR: 30%")
    await ui.update("Обработка OCR: 60%")
    
    # Добавление новой информации
    await ui.append("Найдено 5 позиций")
    
    # Завершение
    await ui.complete("Обработка завершена!", kb=result_keyboard)
    ```
    """
    
    # Константы для форматирования индикатора прогресса
    SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    PROGRESS_INDICATOR = "🔄"
    COMPLETE_INDICATOR = "✅"
    ERROR_INDICATOR = "❌"
    
    def __init__(self, bot: Bot, chat_id: int, throttle_ms: int = 700):
        """
        Инициализация UI-менеджера.
        
        Args:
            bot: Экземпляр бота Aiogram
            chat_id: ID чата для отправки сообщений
            throttle_ms: Минимальное время между обновлениями в миллисекундах
        """
        self.bot = bot
        self.chat_id = chat_id
        self.message: Optional[Message] = None
        self.message_id: Optional[int] = None
        self.current_text: str = ""
        self.lines: List[str] = []
        self.last_update_time: float = 0
        self.throttle_ms = throttle_ms
        self.active = False
        self._spinner_idx = 0
        self._update_task = None
        
    async def start(self, initial_text: str, kb: Optional[InlineKeyboardMarkup] = None) -> Message:
        """
        Запускает UI-сессию с начальным сообщением.
        
        Args:
            initial_text: Начальный текст сообщения
            kb: Опциональная клавиатура (обычно не нужна для начального сообщения)
            
        Returns:
            Message: Объект отправленного сообщения для удобства
        """
        self.active = True
        self.lines = [f"{self.PROGRESS_INDICATOR} {initial_text}"]
        self.current_text = self.lines[0]
        
        # Отправляем начальное сообщение
        self.message = await self.bot.send_message(
            chat_id=self.chat_id,
            text=self.current_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        self.message_id = self.message.message_id
        self.last_update_time = time.time()
        return self.message
    
    async def update(self, text: str, replace_last: bool = True) -> None:
        """
        Обновляет текст сообщения с прогрессом.
        
        Args:
            text: Новый текст для отображения
            replace_last: Если True, заменяет последнюю строку; если False, добавляет новую
        """
        if not self.active or not self.message_id:
            logger.warning("Attempted to update inactive UI")
            return
        
        # Проверка троттлинга
        current_time = time.time()
        time_since_last_update = (current_time - self.last_update_time) * 1000
        
        if time_since_last_update < self.throttle_ms:
            # Слишком рано для следующего обновления, игнорируем
            logger.debug(f"Throttling update: {time_since_last_update}ms < {self.throttle_ms}ms")
            return
            
        # Обновляем последнюю строку или добавляем новую
        if replace_last and self.lines:
            self.lines[-1] = f"{self.PROGRESS_INDICATOR} {text}"
        else:
            self.lines.append(f"{self.PROGRESS_INDICATOR} {text}")
            
        # Обновляем текст и сообщение
        self.current_text = "\n".join(self.lines)
        
        try:
            await edit_message_text_safe(
                bot=self.bot,
                chat_id=self.chat_id,
                msg_id=self.message_id,
                text=self.current_text,
                kb=None  # Не меняем клавиатуру при обновлении прогресса
            )
            self.last_update_time = current_time
        except Exception as e:
            logger.error(f"Error updating UI: {e}")
            
    async def append(self, text: str, indicator: str = "•") -> None:
        """
        Добавляет новую строку к сообщению без изменения статуса.
        
        Args:
            text: Текст для добавления
            indicator: Индикатор для новой строки (по умолчанию - маркер списка)
        """
        await self.update(text, replace_last=False)
        
    async def start_spinner(self, update_ms: int = 200) -> None:
        """
        Запускает анимированный спиннер в последней строке.
        
        Args:
            update_ms: Частота обновления спиннера в миллисекундах
        """
        if self._update_task:
            return  # Уже запущен
            
        async def _spinner_task():
            while self.active:
                if self.lines:
                    # Получаем последнюю строку без индикатора
                    last_line = self.lines[-1]
                    if last_line.startswith(self.PROGRESS_INDICATOR):
                        last_line = last_line[len(self.PROGRESS_INDICATOR):].strip()
                    
                    # Обновляем с анимированным спиннером
                    self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_CHARS)
                    spinner_char = self.SPINNER_CHARS[self._spinner_idx]
                    self.lines[-1] = f"{spinner_char} {last_line}"
                    
                    self.current_text = "\n".join(self.lines)
                    
                    try:
                        await edit_message_text_safe(
                            bot=self.bot,
                            chat_id=self.chat_id,
                            msg_id=self.message_id,
                            text=self.current_text,
                            kb=None
                        )
                    except Exception as e:
                        logger.error(f"Error updating spinner: {e}")
                
                await asyncio.sleep(update_ms / 1000)
        
        self._update_task = asyncio.create_task(_spinner_task())
        
    def stop_spinner(self) -> None:
        """Останавливает анимированный спиннер."""
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None
            
    async def complete(self, text: Optional[str] = None, 
                      kb: Optional[InlineKeyboardMarkup] = None,
                      success: bool = True) -> None:
        """
        Завершает обновление UI с финальным сообщением и опциональной клавиатурой.
        
        Args:
            text: Финальный текст для отображения (если None, использует последнюю строку)
            kb: Финальная клавиатура для отображения
            success: Флаг успешного завершения (влияет на индикатор)
        """
        self.stop_spinner()
        self.active = False
        
        indicator = self.COMPLETE_INDICATOR if success else self.ERROR_INDICATOR
        
        if text:
            # Заменяем последнюю строку с новым индикатором
            if self.lines:
                self.lines[-1] = f"{indicator} {text}"
            else:
                self.lines.append(f"{indicator} {text}")
        elif self.lines:
            # Просто меняем индикатор у последней строки
            last_line = self.lines[-1]
            if last_line.startswith((self.PROGRESS_INDICATOR, *self.SPINNER_CHARS)):
                content = last_line[1:].strip()  # Убираем старый индикатор
                self.lines[-1] = f"{indicator} {content}"
                
        self.current_text = "\n".join(self.lines)
        
        try:
            await edit_message_text_safe(
                bot=self.bot,
                chat_id=self.chat_id,
                msg_id=self.message_id,
                text=self.current_text,
                kb=kb
            )
        except Exception as e:
            logger.error(f"Error completing UI: {e}")
            
    async def error(self, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
        """
        Завершает обновление UI с сообщением об ошибке.
        
        Args:
            text: Текст ошибки для отображения
            kb: Опциональная клавиатура
        """
        await self.complete(text, kb, success=False)
        
    async def delete(self) -> None:
        """Удаляет сообщение с UI."""
        if self.message_id:
            try:
                await self.bot.delete_message(
                    chat_id=self.chat_id,
                    message_id=self.message_id
                )
            except Exception as e:
                logger.error(f"Error deleting UI message: {e}")
                
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