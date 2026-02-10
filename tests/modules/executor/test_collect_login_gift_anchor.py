from types import SimpleNamespace

from app.modules.executor.collect_login_gift import CollectLoginGiftExecutor


def test_extract_anchor_from_debug_with_valid_anchor():
    result = SimpleNamespace(
        debug={
            "anchors": {
                "libaowu_button": {"x": 123, "y": 456, "score": 0.95},
            }
        }
    )

    anchor = CollectLoginGiftExecutor._extract_anchor_from_debug(result, "libaowu")
    assert anchor == (123, 456)


def test_extract_anchor_from_debug_without_debug_or_anchor():
    result_without_debug = SimpleNamespace()
    assert (
        CollectLoginGiftExecutor._extract_anchor_from_debug(
            result_without_debug, "libaowu"
        )
        is None
    )

    result_without_target = SimpleNamespace(
        debug={"anchors": {"other": {"x": 1, "y": 2}}}
    )
    assert (
        CollectLoginGiftExecutor._extract_anchor_from_debug(
            result_without_target, "libaowu"
        )
        is None
    )
