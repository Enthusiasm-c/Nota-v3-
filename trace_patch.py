# Патч для отслеживания инициализации бота
import time
import logging
from functools import wraps

logger = logging.getLogger("startup_trace")
handler = logging.FileHandler("logs/startup_trace.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Декоратор для трассировки функций
def trace_func(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.debug(f"СТАРТ: {func.__module__}.{func.__name__}")
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            logger.debug(f"ЗАВЕРШЕНО: {func.__module__}.{func.__name__} за {end_time - start_time:.2f}с")
            return result
        except Exception as e:
            end_time = time.time()
            logger.error(f"ОШИБКА: {func.__module__}.{func.__name__} - {str(e)} за {end_time - start_time:.2f}с")
            raise
    return wrapper

# Патчим критичные функции в bot.py
try:
    import bot
    
    # Патчим create_bot_and_dispatcher
    original_create_bot = bot.create_bot_and_dispatcher
    bot.create_bot_and_dispatcher = trace_func(original_create_bot)
    
    # Патчим main
    if hasattr(bot, 'main'):
        original_main = bot.main
        bot.main = trace_func(original_main)
    
    # Патчим register_handlers
    original_register = bot.register_handlers
    bot.register_handlers = trace_func(original_register)
    
    # Трассируем API-клиенты
    try:
        import app.config
        from app.config import get_ocr_client, get_chat_client
        
        app.config.get_ocr_client = trace_func(get_ocr_client)
        app.config.get_chat_client = trace_func(get_chat_client)
        
        logger.debug("Успешно добавлена трассировка к API клиентам")
    except Exception as e:
        logger.error(f"Ошибка при патче API клиентов: {str(e)}")
    
    logger.debug("Успешно добавлена трассировка к ключевым функциям")
except Exception as e:
    logger.error(f"Ошибка добавления трассировки: {str(e)}")
