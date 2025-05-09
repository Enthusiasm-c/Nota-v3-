import contextvars

# Глобальный contextvar для trace_id
trace_id_var = contextvars.ContextVar("trace_id", default=None)

def set_trace_id(trace_id: str):
    trace_id_var.set(trace_id)

def get_trace_id() -> str:
    return trace_id_var.get()
