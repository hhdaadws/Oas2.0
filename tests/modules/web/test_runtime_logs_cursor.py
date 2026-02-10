from app.modules.web.routers.tasks import _format_runtime_cursor, _parse_runtime_cursor


def test_runtime_cursor_parser_handles_values():
    assert _parse_runtime_cursor(None) is None
    assert _parse_runtime_cursor("") is None
    assert _parse_runtime_cursor("abc") is None
    assert _parse_runtime_cursor("1700000000.25") == 1700000000.25


def test_runtime_cursor_formatter_precision():
    cursor = _format_runtime_cursor(1700000000.1234567)
    assert cursor == "1700000000.123457"
