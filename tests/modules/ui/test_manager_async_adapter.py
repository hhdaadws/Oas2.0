from types import SimpleNamespace

import pytest

from app.modules.emu.async_adapter import AsyncEmulatorAdapter
from app.modules.ui.manager import UIManager


class _DummySyncAdapter:
    def __init__(self):
        self.cfg = SimpleNamespace(
            adb_addr="127.0.0.1:16384",
            pkg_name="com.test.game",
        )
        self.adb = SimpleNamespace(
            is_app_running=lambda *_: False,
            tap=lambda *_: None,
        )
        self.ipc = object()
        self.mumu = None

    def capture_ndarray(self, method="adb"):
        return None

    def tap(self, x, y):
        return None

    def start_app(self, mode="adb_monkey", activity=None):
        return None

    def stop_app(self):
        return None


@pytest.mark.asyncio
async def test_manager_uses_async_adapter_adb_helpers():
    sync_adapter = _DummySyncAdapter()
    adapter = AsyncEmulatorAdapter(sync_adapter)
    manager = UIManager(adapter=adapter)

    calls = {"is_running": 0, "tap": []}

    async def _fake_is_running():
        calls["is_running"] += 1
        return True

    async def _fake_adb_tap(x, y):
        calls["tap"].append((x, y))

    adapter.adb_is_app_running = _fake_is_running
    adapter.adb_tap = _fake_adb_tap

    assert await manager._is_app_running() is True
    await manager._adb_tap(100, 200)

    assert calls["is_running"] == 1
    assert calls["tap"] == [(100, 200)]
