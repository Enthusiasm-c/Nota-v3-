"""
Enhanced logger configuration with buffering and optimization.
"""

import logging
import logging.handlers
import os
import time
import threading

# Buffer for non-critical logs
log_buffer = []
log_buffer_lock = threading.Lock()
MAX_BUFFER_SIZE = 100
last_flush_time = time.time()
FLUSH_INTERVAL = 5  # seconds

# Log levels configuration for different environments
LOG_LEVELS = {
    "production": {
        "default": logging.INFO,
        "aiogram": logging.WARNING,
        "httpx": logging.WARNING,
        "openai": logging.WARNING,
        "urllib3": logging.WARNING,
        "asyncio": logging.ERROR,
        "matplotlib": logging.WARNING,
    },
    "development": {
        "default": logging.DEBUG,
        "aiogram": logging.INFO,
        "httpx": logging.WARNING,
        "openai": logging.INFO,
        "urllib3": logging.WARNING,
        "asyncio": logging.WARNING,
        "matplotlib": logging.WARNING,
    }
}

# Flag to track if logging has already been configured
_logging_configured = False

def configure_logging(environment="development", log_dir="logs"):
    """
    Configures application logging with optimized settings.
    
    Args:
        environment: "production" or "development"
        log_dir: Directory for log files
    """
    global _logging_configured
    
    # Only configure logging once - prevent duplicate handlers
    if _logging_configured:
        logging.getLogger("app").debug("Logging already configured - skipping")
        return
        
    os.makedirs(log_dir, exist_ok=True)
    
    # First, remove all existing handlers to avoid duplication
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Get log levels for current environment
    levels = LOG_LEVELS.get(environment, LOG_LEVELS["development"])
    
    # Configure root logger
    root_logger.setLevel(levels["default"])
    
    # Console handler with more detailed format for development
    console = logging.StreamHandler()
    if environment == "development":
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "\033[1;36m%(asctime)s\033[0m - \033[1;33m%(name)s\033[0m - \033[1;35m%(levelname)s\033[0m - %(message)s"
        ))
    else:
        console.setLevel(levels["default"])
        console.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
    root_logger.addHandler(console)
    
    # Main bot log file
    bot_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/bot.log", 
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5
    )
    bot_handler.setLevel(levels["default"])
    bot_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root_logger.addHandler(bot_handler)
    
    # General application log
    file_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/nota.log", 
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(levels["default"])
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root_logger.addHandler(file_handler)
    
    # Separate file for errors
    error_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/errors.log", 
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root_logger.addHandler(error_handler)
    
    # Configure specific module levels
    for module, level in levels.items():
        if module != "default":
            logging.getLogger(module).setLevel(level)
    
    # Log configuration success
    logging.getLogger("app").info(f"Logging configured for {environment} environment with {len(root_logger.handlers)} handlers")
    
    # Mark logging as configured
    _logging_configured = True

def get_buffered_logger(name):
    """
    Returns a buffered logger that reduces I/O for non-critical logs.
    
    Args:
        name: Logger name
        
    Returns:
        BufferedLogger instance
    """
    return BufferedLogger(logging.getLogger(name))

class BufferedLogger:
    """
    Logger wrapper that buffers non-critical log messages.
    """
    
    def __init__(self, logger):
        self.logger = logger
    
    def debug(self, message, *args, **kwargs):
        _buffered_log(self.logger, logging.DEBUG, message, *args, **kwargs)
    
    def info(self, message, *args, **kwargs):
        _buffered_log(self.logger, logging.INFO, message, *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        # Warnings and above are logged immediately
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message, *args, **kwargs):
        self.logger.critical(message, *args, **kwargs)

def _buffered_log(logger, level, message, *args, **kwargs):
    """
    Adds a log message to the buffer and flushes if needed.
    """
    global log_buffer, last_flush_time
    
    with log_buffer_lock:
        # Add to buffer
        log_buffer.append((logger, level, message, args, kwargs))
        
        current_time = time.time()
        buffer_full = len(log_buffer) >= MAX_BUFFER_SIZE
        timeout_reached = current_time - last_flush_time > FLUSH_INTERVAL
        
        # Flush if buffer is full, too old, or on error
        if buffer_full or timeout_reached or level >= logging.WARNING:
            flush_log_buffer()
            last_flush_time = current_time

def flush_log_buffer():
    """
    Flushes all buffered log messages.
    """
    global log_buffer
    
    with log_buffer_lock:
        for logger, level, message, args, kwargs in log_buffer:
            # Direct log call
            logger._log(level, message, args, **kwargs)
        
        # Clear buffer
        log_buffer = []