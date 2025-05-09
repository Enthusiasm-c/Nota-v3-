import logging
from functools import wraps
from app.trace_context import get_trace_id

logger = logging.getLogger(__name__)

def trace_openai(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        trace_id = get_trace_id()
        logger.info("OpenAI call: prompt", extra={"trace_id": trace_id, "data": {"args": args, "kwargs": kwargs}})
        try:
            result = func(*args, **kwargs)
            logger.info("OpenAI call: result", extra={"trace_id": trace_id, "data": {"result": result}})
            return result
        except Exception as e:
            logger.error("OpenAI call: exception", extra={"trace_id": trace_id, "data": {"error": str(e)}})
            raise
    return wrapper
