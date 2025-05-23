from app.models import ParsedData


def test_parsed_to_dict_success():
    from app.converters import parsed_to_dict

    parsed = ParsedData(date=None, positions=[])
    result = parsed_to_dict(parsed)
    assert isinstance(result, dict)
    assert "positions" in result
    assert result["positions"] == []
