import logging
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from app.trace_context import get_trace_id
import os

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "assistant_trace.log")

class JsonTraceFormatter(logging.Formatter):
    def format(self, record):
        trace_id = get_trace_id() or getattr(record, "trace_id", None)
        log_entry = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "lvl": record.levelname,
            "trace": trace_id,
            "mod": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "data"):
            log_entry["data"] = record.data
        return json.dumps(log_entry, ensure_ascii=False)

def setup_json_trace_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8")
    handler.setFormatter(JsonTraceFormatter())
    logger.addHandler(handler)
    return logger
