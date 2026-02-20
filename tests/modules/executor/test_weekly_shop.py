from types import SimpleNamespace

import pytest

from app.core.constants import TaskStatus
from app.modules.executor.weekly_shop import WeeklyShopExecutor


class _DummyPopupHandler:
    async def check_and_dismiss(self, screenshot):
        return 0


class _DummyUI:
    def __init__(self):
        self.capture_method = "adb"
        self.popup_handler = _DummyPopupHandler()

    async def ensure_game_ready(self, timeout=90.0):
        return True

    async def ensure_ui(self, ui_name, max_steps=10, step_timeout=3.0):
        return True


@pytest.mark.asyncio
async def test_weekly_shop_execute_never_swipes_when_retrying_item_search(monkeypatch):
    executor = WeeklyShopExecutor(worker_id=1, emulator_id=1)
    executor.current_account = SimpleNamespace(id=1, login_id="acc_1")
    executor.shared_ui = _DummyUI()

    async def fake_click_template(*args, **kwargs):
        return True

    monkeypatch.setattr("app.modules.executor.weekly_shop.click_template", fake_click_template)

    async def fake_capture():
        return object()

    executor._capture = fake_capture

    async def fake_read_xunzhang(screenshot):
        return 999

    executor._read_xunzhang = fake_read_xunzhang
    executor._get_buy_options = lambda: {
        "buy_lanpiao": True,
        "buy_heidan": False,
        "buy_tili": False,
    }

    match_calls = {"count": 0}

    def fake_match_template(screenshot, template_path):
        match_calls["count"] += 1
        if match_calls["count"] == 1:
            return None
        return object()

    monkeypatch.setattr("app.modules.executor.weekly_shop.match_template", fake_match_template)

    async def fake_read_remaining(screenshot, match):
        return 1

    executor._read_remaining = fake_read_remaining

    async def fake_buy_item(template_name, label):
        return False

    executor._buy_item = fake_buy_item
    executor._update_xunzhang_in_db = lambda value: None
    executor._update_next_time = lambda *, all_done: None

    swipe_calls = {"count": 0}

    async def fake_swipe(*args, **kwargs):
        swipe_calls["count"] += 1

    executor._swipe = fake_swipe

    result = await executor.execute()

    assert result["status"] == TaskStatus.SUCCEEDED
    assert swipe_calls["count"] == 0


@pytest.mark.asyncio
async def test_weekly_shop_dismiss_popups_skip_click_when_no_reward(monkeypatch):
    executor = WeeklyShopExecutor(worker_id=1, emulator_id=1)
    executor.ui = _DummyUI()

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("app.modules.executor.weekly_shop.asyncio.sleep", fake_sleep)

    async def fake_capture():
        return object()

    executor._capture = fake_capture

    def fake_match_template(screenshot, template_path):
        return None

    monkeypatch.setattr("app.modules.executor.weekly_shop.match_template", fake_match_template)

    tap_calls = {"count": 0}

    async def fake_tap(x, y):
        tap_calls["count"] += 1

    executor._tap = fake_tap

    await executor._dismiss_popups()

    assert tap_calls["count"] == 0
