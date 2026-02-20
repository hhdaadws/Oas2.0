from types import SimpleNamespace

import pytest

from app.modules.emu import async_adapter as async_adapter_module
from app.modules.emu.async_adapter import AsyncEmulatorAdapter


class _DummyAdb:
    def is_app_running(self, addr, pkg):
        return True

    def tap(self, addr, x, y):
        return None

    def shell(self, addr, cmd, timeout=30.0):
        return 0, f"{addr}:{cmd}:{timeout}"

    def force_stop(self, addr, pkg):
        return None

    def root(self, addr):
        return True


class _DummySyncAdapter:
    def __init__(self):
        self.cfg = SimpleNamespace(
            adb_addr="127.0.0.1:16384",
            pkg_name="com.test.game",
        )
        self.adb = _DummyAdb()
        self.ipc = object()
        self.mumu = None

    def ensure_running(self):
        return True

    def start_app(self, mode="adb_monkey", activity=None):
        return (mode, activity)

    def stop_app(self):
        return None

    def capture(self, method="adb"):
        return b"png"

    def capture_ndarray(self, method="adb"):
        return f"ndarray:{method}"

    def tap(self, x, y):
        return (x, y)

    def swipe(self, x1, y1, x2, y2, dur_ms=300):
        return (x1, y1, x2, y2, dur_ms)

    def push_login_data(self, login_id, data_dir="putonglogindata"):
        return f"{login_id}:{data_dir}"

    def foreground(self):
        return True


@pytest.mark.asyncio
async def test_async_adapter_core_ops_route_to_same_io_key(monkeypatch):
    calls = []

    async def _fake_run_in_emulator_io(io_key, func, *args):
        calls.append((io_key, args))
        return func(*args)

    monkeypatch.setattr(
        async_adapter_module,
        "run_in_emulator_io",
        _fake_run_in_emulator_io,
    )

    sync_adapter = _DummySyncAdapter()
    adapter = AsyncEmulatorAdapter(sync_adapter)

    assert await adapter.ensure_running() is True
    assert await adapter.capture("adb") == b"png"
    assert await adapter.tap(1, 2) == (1, 2)
    assert await adapter.swipe(1, 2, 3, 4, 500) == (1, 2, 3, 4, 500)
    assert await adapter.push_login_data("acc-1") == "acc-1:putonglogindata"

    assert calls
    assert all(io_key == sync_adapter.cfg.adb_addr for io_key, _ in calls)


@pytest.mark.asyncio
async def test_async_adapter_adb_helpers_route_to_same_io_key(monkeypatch):
    calls = []

    async def _fake_run_in_emulator_io(io_key, func, *args):
        calls.append((io_key, args))
        return func(*args)

    monkeypatch.setattr(
        async_adapter_module,
        "run_in_emulator_io",
        _fake_run_in_emulator_io,
    )

    sync_adapter = _DummySyncAdapter()
    adapter = AsyncEmulatorAdapter(sync_adapter)

    assert await adapter.adb_is_app_running() is True
    assert await adapter.adb_tap(10, 11) is None
    assert await adapter.adb_shell("echo test") == (
        0,
        "127.0.0.1:16384:echo test:30.0",
    )
    assert await adapter.adb_force_stop("com.test.game") is None
    assert await adapter.adb_root() is True

    assert calls
    assert all(io_key == sync_adapter.cfg.adb_addr for io_key, _ in calls)
