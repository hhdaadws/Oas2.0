import asyncio
import sys
import types

import pytest

if "loguru" not in sys.modules:
    class _DummyLogger:
        def bind(self, **kwargs):
            return self

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    sys.modules["loguru"] = types.SimpleNamespace(logger=_DummyLogger())

from app.modules.ui.default_popups import register_default_popups
from app.modules.ui.popup_handler import PopupHandler
from app.modules.ui.popups import DismissAction, DismissType, PopupDef, PopupRegistry
from app.modules.ui.registry import TemplateDef


class DummyADB:
    def __init__(self) -> None:
        self.taps = []

    def tap(self, addr: str, x: int, y: int) -> None:
        self.taps.append((addr, x, y))

    def shell(self, addr: str, cmd: str) -> None:
        return None


class DummyCfg:
    adb_addr = "127.0.0.1:7555"


class DummyAdapter:
    def __init__(self) -> None:
        self.cfg = DummyCfg()
        self.adb = DummyADB()

    def capture_ndarray(self, method: str = "adb"):
        return None


def _build_popup(action: DismissAction) -> PopupDef:
    return PopupDef(
        id="test_popup",
        label="测试弹窗",
        detect_template=TemplateDef(name="test_popup", path="assets/ui/templates/popup_5.png"),
        dismiss_actions=[action],
        priority=50,
    )


def test_tap_action_with_tap_rect_clicks_inside_region(monkeypatch):
    adapter = DummyAdapter()
    handler = PopupHandler(adapter)
    popup = _build_popup(
        DismissAction(
            type=DismissType.TAP,
            tap_rect=(314, 341, 425, 383),
            post_delay_ms=0,
        )
    )

    calls = []
    values = iter([320, 360])

    def fake_randint(start: int, end: int) -> int:
        calls.append((start, end))
        return next(values)

    monkeypatch.setattr("app.modules.ui.popup_handler.random.randint", fake_randint)

    ok = asyncio.run(handler.dismiss(popup))

    assert ok is True
    assert calls == [(314, 425), (341, 383)]
    assert adapter.adb.taps == [("127.0.0.1:7555", 320, 360)]
    _, x, y = adapter.adb.taps[0]
    assert 314 <= x <= 425
    assert 341 <= y <= 383


def test_tap_action_without_tap_rect_keeps_fixed_click():
    adapter = DummyAdapter()
    handler = PopupHandler(adapter)
    popup = _build_popup(
        DismissAction(
            type=DismissType.TAP,
            tap_x=480,
            tap_y=270,
            post_delay_ms=0,
        )
    )

    ok = asyncio.run(handler.dismiss(popup))

    assert ok is True
    assert adapter.adb.taps == [("127.0.0.1:7555", 480, 270)]


def test_default_popup5_uses_tap_rect_for_second_action():
    reg = PopupRegistry()
    register_default_popups(reg)
    popup = reg.get("popup_5")

    assert popup is not None
    assert len(popup.dismiss_actions) >= 2

    action = popup.dismiss_actions[1]
    assert action.type == DismissType.TAP
    assert action.tap_rect == (314, 341, 425, 383)
    assert action.template_path == ""
