import inspect
from app import matcher, formatter


def test_matcher_signature():
    params = list(inspect.signature(matcher.match_positions).parameters.keys())
    assert params[:2] == ["positions", "products"]


def test_formatter_signature():
    sig = inspect.signature(formatter.build_report)
    params = list(sig.parameters.keys())
    assert len(params) >= 2
    assert params[0] == "parsed_data"
    assert params[1] == "match_results"
