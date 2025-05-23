"""
Utility for incremental user interface updates in Telegram.

Provides a convenient interface for showing progress of long operations,
with support for animated indicators and real-time status updates.
"""

import asyncio
import logging
import time
from typing import Any, Callable, List, Optional

from aiogram.types import InlineKeyboardMarkup, Message

from app.bot_utils import edit_message_text_safe

logger = logging.getLogger(__name__)

# Spinner themes
SPINNER_THEMES = {
    "default": [
        "(   •   )",
        "(  •    )",
        "( •     )",
        "(•      )",
        "( •     )",
        "(  •    )",
        "(   •   )",
        "(    •  )",
        "(     • )",
        "(      •)",
        "(     • )",
        "(    •  )",
    ],
    "dots": [
        "(   •   )",
        "(  •    )",
        "( •     )",
        "(•      )",
        "( •     )",
        "(  •    )",
        "(   •   )",
        "(    •  )",
        "(     • )",
        "(      •)",
        "(     • )",
        "(    •  )",
    ],
    "ball": [
        "(   •   )",
        "(  •    )",
        "( •     )",
        "(•      )",
        "( •     )",
        "(  •    )",
        "(   •   )",
        "(    •  )",
        "(     • )",
        "(      •)",
        "(     • )",
        "(    •  )",
    ],
}


class IncrementalUI:
    """
    Class for incremental user interface updates in Telegram.

    Allows showing progress of long operations by updating the same message,
    instead of sending multiple messages. Supports animated indicators
    and various visualization themes.

    Attributes:
        bot: Telegram bot instance
        chat_id: Chat ID where the message is displayed
        message_id: ID of the message being updated
        text: Current message text
        _spinner_task: Async task for spinner animation
        _spinner_running: Flag indicating if spinner is running
    """

    def __init__(self, bot, chat_id: int):
        """
        Initializes new UI for incremental updates.

        Args:
            bot: Telegram bot instance
            chat_id: Chat ID for sending messages
        """
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = None
        self.text = ""
        self._spinner_task = None
        self._spinner_running = False
        self._theme = "default"
        self._start_time = None

    async def start(self, initial_text: str = "Starting...") -> None:
        """
        Starts a new sequence of updates with initial text.

        Args:
            initial_text: Initial message text
        """
        self._start_time = time.time()
        self.text = initial_text
        try:
            message = await self.bot.send_message(self.chat_id, initial_text)
            self.message_id = message.message_id
            logger.debug(f"Started UI: message_id={self.message_id}")
        except Exception as e:
            logger.error(f"Error starting UI: {e}")
            self.message_id = None

    async def update(self, text: str) -> None:
        """
        Updates message text.

        Args:
            text: New message text
        """
        if self.message_id is None:
            logger.warning("Update attempted before UI start")
            return

        self.text = text

        try:
            await self.bot.edit_message_text(text, chat_id=self.chat_id, message_id=self.message_id)
            logger.debug(f"Updated: {text[:30]}...")
        except Exception as e:
            logger.warning(f"Update failed: {e}")

    async def append(self, new_text: str) -> None:
        """
        Appends new text to existing message.

        Args:
            new_text: Text to append
        """
        self.text = f"{self.text}\n{new_text}"
        await self.update(self.text)

    async def complete(
        self, completion_text: Optional[str] = None, kb: Optional[InlineKeyboardMarkup] = None
    ) -> None:
        """
        Completes update sequence with optional final text and keyboard.

        Args:
            completion_text: Final text to display
            kb: Optional keyboard to add to message
        """
        self.stop_spinner()

        elapsed = time.time() - self._start_time if self._start_time else 0
        elapsed_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""

        if completion_text:
            final_text = f"{self.text}\n{completion_text}{elapsed_str}"
        else:
            final_text = f"{self.text}\nDone{elapsed_str}"

        try:
            if kb:
                await self.bot.edit_message_text(
                    final_text, chat_id=self.chat_id, message_id=self.message_id, reply_markup=kb
                )
            else:
                await self.update(final_text)
        except Exception as e:
            logger.error(f"Complete failed: {e}")
            try:
                await edit_message_text_safe(
                    bot=self.bot,
                    chat_id=self.chat_id,
                    msg_id=self.message_id,
                    text=final_text,
                    kb=kb,
                )
            except Exception as e2:
                logger.error(f"Safe edit failed: {e2}")

    async def complete_with_keyboard(
        self, final_text: str, has_errors: bool = False, lang: str = "en"
    ) -> None:
        """
        Completes update sequence with standard keyboard depending on errors presence.

        Args:
            final_text: Final text to display
            has_errors: Error presence flag, affects "Confirm" button display
            lang: Language for internationalization
        """
        from app.keyboards import build_main_kb

        logger.info(f"Building keyboard: has_errors={has_errors}")

        keyboard = build_main_kb(has_errors=has_errors, lang=lang)

        await self.complete(final_text, kb=keyboard)
        logger.info("Completed with keyboard")

    async def error(self, error_text: str, show_timing: bool = False) -> None:
        """
        Shows error message.

        Args:
            error_text: Error text to display
            show_timing: Whether to show execution time
        """
        self.stop_spinner()

        elapsed_str = ""
        if show_timing and self._start_time:
            elapsed = time.time() - self._start_time
            elapsed_str = f" ({elapsed:.1f}s)"

        await self.update(f"{self.text}\n❌ {error_text}{elapsed_str}")

    def stop_spinner(self) -> None:
        """Stops spinner animation if it's running."""
        if self._spinner_running and self._spinner_task:
            self._spinner_running = False
            if not self._spinner_task.done():
                self._spinner_task.cancel()

    async def start_spinner(self, show_text: bool = True, theme: str = "default") -> None:
        """
        Starts animated spinner, updating message.

        Args:
            show_text: Whether to show text along with spinner
            theme: Spinner theme (default, dots, ball, etc.)
        """
        if self._spinner_running:
            return

        if theme not in SPINNER_THEMES:
            theme = "default"

        self._theme = theme
        self._spinner_running = True

        try:
            self._spinner_task = asyncio.create_task(
                self._animate_spinner(SPINNER_THEMES[theme], show_text)
            )
        except Exception as e:
            logger.error(f"Spinner start failed: {e}")
            self._spinner_running = False

    async def _animate_spinner(self, frames: List[str], show_text: bool) -> None:
        """
        Internal method for spinner animation.

        Args:
            frames: Spinner animation frames
            show_text: Whether to show text along with spinner
        """
        i = 0
        try:
            while self._spinner_running:
                frame = frames[i % len(frames)]

                if show_text:
                    spinner_text = f"{frame} {self.text}"
                else:
                    lines = self.text.split("\n")
                    lines[-1] = f"{lines[-1]} {frame}"
                    spinner_text = "\n".join(lines)

                try:
                    await self.bot.edit_message_text(
                        spinner_text, chat_id=self.chat_id, message_id=self.message_id
                    )
                except Exception as e:
                    logger.debug(f"Spinner update error (normal during rapid updates): {e}")

                i += 1
                await asyncio.sleep(0.3)  # Update interval
        except asyncio.CancelledError:
            logger.debug("Spinner animation cancelled")
        except Exception as e:
            logger.error(f"Error in spinner animation: {e}")
            self._spinner_running = False

    @staticmethod
    async def with_progress(
        message: Message,
        initial_text: str,
        process_func: Callable,
        final_text: Optional[str] = None,
        final_kb: Optional[InlineKeyboardMarkup] = None,
        error_text: Optional[str] = None,
    ) -> Any:
        """
        Executes function with progress UI and returns result.

        Args:
            message: Message to take chat_id and bot from
            initial_text: Initial indicator text
            process_func: Async function to be called with ui as argument
            final_text: Final text on success
            final_kb: Final keyboard on success
            error_text: Error text template

        Returns:
            Result of process_func
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
            error_msg = error_text or f"Error occurred: {str(e)}"
            await ui.error(error_msg)
            raise
