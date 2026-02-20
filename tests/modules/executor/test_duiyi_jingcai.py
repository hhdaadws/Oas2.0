from types import SimpleNamespace

import numpy as np
import pytest

from app.modules.executor.duiyi_jingcai import DuiyiJingcaiExecutor


@pytest.mark.asyncio
async def test_handle_dy_bet_requires_popup_jinbi_before_jingcai(monkeypatch):
    executor = DuiyiJingcaiExecutor(worker_id=1, emulator_id=1)
    executor.adapter = object()
    executor.ui = SimpleNamespace(capture_method="adb")

    class _FakeMatch:
        score = 0.99

        def random_point(self):
            return 100, 200

    async def fake_capture():
        return object()

    async def fake_tap(_x, _y):
        return None

    def fake_find_direction_buttons(_screenshot):
        m = _FakeMatch()
        return m, m

    clicked_templates = []
    dismiss_calls = {"count": 0}

    async def fake_rapid_click_template(template, **_kwargs):
        clicked_templates.append(template)
        return True

    async def fake_dismiss_popup_jinbi():
        dismiss_calls["count"] += 1
        return False

    monkeypatch.setattr(executor, "_capture", fake_capture)
    monkeypatch.setattr(executor, "_tap", fake_tap)
    monkeypatch.setattr(executor, "_find_direction_buttons", fake_find_direction_buttons)
    monkeypatch.setattr(executor, "_rapid_click_template", fake_rapid_click_template)
    monkeypatch.setattr(executor, "_dismiss_popup_jinbi", fake_dismiss_popup_jinbi)

    ok = await executor._handle_dy_bet("\u5de6")

    assert ok is False
    assert dismiss_calls["count"] == 3
    assert executor._TPL_DY_30 in clicked_templates
    assert executor._TPL_DY_JINGCAI not in clicked_templates


@pytest.mark.asyncio
async def test_handle_dy_bet_clicks_jingcai_after_popup_jinbi_closed(monkeypatch):
    executor = DuiyiJingcaiExecutor(worker_id=1, emulator_id=1)
    executor.adapter = object()
    executor.ui = SimpleNamespace(capture_method="adb")

    class _FakeMatch:
        score = 0.99

        def random_point(self):
            return 110, 210

    async def fake_capture():
        return object()

    async def fake_tap(_x, _y):
        return None

    def fake_find_direction_buttons(_screenshot):
        m = _FakeMatch()
        return m, m

    clicked_templates = []

    async def fake_rapid_click_template(template, **_kwargs):
        clicked_templates.append(template)
        return True

    async def fake_dismiss_popup_jinbi():
        return True

    async def fake_wait_for_template(*_args, **_kwargs):
        return SimpleNamespace(score=0.95)

    monkeypatch.setattr(executor, "_capture", fake_capture)
    monkeypatch.setattr(executor, "_tap", fake_tap)
    monkeypatch.setattr(executor, "_find_direction_buttons", fake_find_direction_buttons)
    monkeypatch.setattr(executor, "_rapid_click_template", fake_rapid_click_template)
    monkeypatch.setattr(executor, "_dismiss_popup_jinbi", fake_dismiss_popup_jinbi)
    monkeypatch.setattr(
        "app.modules.executor.duiyi_jingcai.wait_for_template",
        fake_wait_for_template,
    )

    ok = await executor._handle_dy_bet("\u5de6")

    assert ok is True
    assert clicked_templates[:3] == [
        executor._TPL_DY_30,
        executor._TPL_DY_JINGCAI,
        executor._TPL_DY_QUEDING,
    ]


@pytest.mark.asyncio
async def test_handle_dy_win_requires_jiangli_closed_confirmation(monkeypatch):
    executor = DuiyiJingcaiExecutor(worker_id=1, emulator_id=1)
    executor.adapter = object()
    executor.ui = SimpleNamespace(capture_method="adb")

    tap_calls = []

    async def fake_wait_for_template(*_args, **_kwargs):
        return SimpleNamespace(score=0.99)

    async def fake_capture():
        return np.zeros((540, 960, 3), dtype=np.uint8)

    def fake_match_template(_gray, template, **_kwargs):
        if template == executor._TPL_DY_NEXT:
            return None
        return None

    async def fake_tap(x, y):
        tap_calls.append((x, y))

    async def fake_ensure_jiangli_closed(**_kwargs):
        return False

    monkeypatch.setattr(
        "app.modules.executor.duiyi_jingcai.wait_for_template",
        fake_wait_for_template,
    )
    monkeypatch.setattr("app.modules.executor.duiyi_jingcai.match_template", fake_match_template)
    monkeypatch.setattr(executor, "_capture", fake_capture)
    monkeypatch.setattr(executor, "_tap", fake_tap)
    monkeypatch.setattr(executor, "_ensure_jiangli_closed", fake_ensure_jiangli_closed)
    monkeypatch.setattr("random.randint", lambda a, _b: a)

    ok = await executor._handle_dy_win()

    assert ok is False
    assert tap_calls, "应先执行领奖点击，再因弹窗确认失败返回 False"


@pytest.mark.asyncio
async def test_handle_dy_next_stops_when_popup_not_cleared(monkeypatch):
    executor = DuiyiJingcaiExecutor(worker_id=1, emulator_id=1)
    executor.adapter = object()
    executor.ui = SimpleNamespace(capture_method="adb")

    rapid_called = {"value": False}

    async def fake_ensure_jiangli_closed(**_kwargs):
        return False

    async def fake_rapid_click_template(*_args, **_kwargs):
        rapid_called["value"] = True
        return True

    monkeypatch.setattr(executor, "_ensure_jiangli_closed", fake_ensure_jiangli_closed)
    monkeypatch.setattr(executor, "_rapid_click_template", fake_rapid_click_template)

    ok = await executor._handle_dy_next()

    assert ok is False
    assert rapid_called["value"] is False
