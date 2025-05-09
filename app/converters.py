from app.models import ParsedData

def parsed_to_dict(p) -> dict:
    """Универсальный конвертер ParsedData или dict -> dict (Pydantic v2)."""
    if hasattr(p, "model_dump"):
        return p.model_dump()
    if isinstance(p, dict):
        return p
    raise TypeError(f"Cannot convert object of type {type(p)} to dict")
