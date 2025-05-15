import pytest
from app.actions import error_monitor
from datetime import datetime


def test_parse_traceback_basic():
    lines = [
        "2024-05-13 12:00:00,123 ERROR: AttributeError: 'Foo' object has no attribute 'bar'",
        '  File "app/foo.py", line 42, in <module>',
        '    foo.bar()',
    ]
    analyzer = error_monitor.ErrorAnalyzer()
    ctx = analyzer.parse_traceback(lines)
    assert ctx.error_type == "AttributeError"
    assert "no attribute" in ctx.error_message
    assert ctx.file_path == "app/foo.py"
    assert ctx.line_number == 42
    assert isinstance(ctx.traceback, list)


def test_analyze_error_attribute():
    ctx = error_monitor.ErrorContext(
        timestamp=datetime.now(),
        error_type="AttributeError",
        error_message="'Foo' object has no attribute 'bar'",
        traceback=[],
        file_path="app/foo.py",
        line_number=42,
        code_snippet=None,
    )
    analyzer = error_monitor.ErrorAnalyzer()
    suggestion = analyzer.analyze_error(ctx)
    assert suggestion is not None
    assert "атрибут" in suggestion


def test_analyze_error_typeerror():
    ctx = error_monitor.ErrorContext(
        timestamp=datetime.now(),
        error_type="TypeError",
        error_message="'int' object is not callable",
        traceback=[],
        file_path="app/bar.py",
        line_number=10,
        code_snippet=None,
    )
    analyzer = error_monitor.ErrorAnalyzer()
    suggestion = analyzer.analyze_error(ctx)
    assert suggestion is not None
    assert "Объект не является функцией" in suggestion


def test_analyze_error_importerror():
    ctx = error_monitor.ErrorContext(
        timestamp=datetime.now(),
        error_type="ModuleNotFoundError",
        error_message="No module named 'baz'",
        traceback=[],
        file_path="app/baz.py",
        line_number=5,
        code_snippet=None,
    )
    analyzer = error_monitor.ErrorAnalyzer()
    suggestion = analyzer.analyze_error(ctx)
    assert suggestion is not None
    assert "модуль" in suggestion


def test_monitor_log_file_not_found(tmp_path):
    log_path = tmp_path / "not_exists.log"
    analyzer = error_monitor.ErrorAnalyzer(str(log_path))
    result = analyzer.monitor_log()
    assert result is None


def test_monitor_log_with_traceback(tmp_path):
    log_path = tmp_path / "test.log"
    log_content = (
        "2024-05-13 12:00:00,123 ERROR: Something happened\n"
        "Traceback (most recent call last)\n"
        "  File \"app/foo.py\", line 42, in <module>\n"
        "    foo.bar()\n"
        "AttributeError: 'Foo' object has no attribute 'bar'\n"
    )
    log_path.write_text(log_content)
    analyzer = error_monitor.ErrorAnalyzer(str(log_path))
    result = analyzer.monitor_log()
    assert result is not None
    assert "атрибут" in result 