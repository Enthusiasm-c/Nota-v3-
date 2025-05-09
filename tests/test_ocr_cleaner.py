from app.ocr_cleaner import clean_ocr_response
from app.models import ParsedData, Position


def test_cleaner_positions_only():
    # Payload with only positions
    payload = '{"positions": [{"name": "Тунец", "qty": 2, "unit": "kg"}]}'
    cleaned = clean_ocr_response(payload)
    data = ParsedData.model_validate(cleaned)
    assert data.supplier is None
    assert data.date is None
    assert len(data.positions) == 1
    assert data.positions[0].name == "Тунец"
    assert data.positions[0].qty == 2
    assert data.positions[0].unit == "kg"
