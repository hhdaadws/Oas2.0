"""
异步 EmulatorAdapter 包装器

将同步的 EmulatorAdapter 方法通过线程池转为异步方法，
使其在 asyncio 事件循环中不阻塞其他 Worker。

使用方式：
    adapter = EmulatorAdapter(cfg)
    async_adapter = AsyncEmulatorAdapter(adapter)
    screenshot = await async_adapter.capture()  # 不阻塞事件循环
"""
from __future__ import annotations

import functools
from typing import Optional

from ...core.thread_pool import run_in_emulator_io
from .adapter import EmulatorAdapter, AdapterConfig


class AsyncEmulatorAdapter:
    """EmulatorAdapter 的异步包装器（代理模式）。

    所有 I/O 阻塞方法通过 run_in_emulator_io offload 到线程池执行，
    释放 asyncio 事件循环给其他 Worker。
    """

    def __init__(self, adapter: EmulatorAdapter) -> None:
        self._sync = adapter
        self._io_key = adapter.cfg.adb_addr

    @property
    def sync(self) -> EmulatorAdapter:
        """获取底层同步适配器。"""
        return self._sync

    @property
    def cfg(self) -> AdapterConfig:
        return self._sync.cfg

    @property
    def adb(self):
        return self._sync.adb

    @property
    def ipc(self):
        return self._sync.ipc

    @property
    def mumu(self):
        return self._sync.mumu

    # ── 心跳代理（轻量操作，无需 offload） ──

    @staticmethod
    def touch_heartbeat(adb_addr: str) -> None:
        EmulatorAdapter.touch_heartbeat(adb_addr)

    @staticmethod
    def get_heartbeat(adb_addr: str) -> float:
        return EmulatorAdapter.get_heartbeat(adb_addr)

    # ── 异步方法 ──

    async def _run(self, func, *args):
        return await run_in_emulator_io(self._io_key, func, *args)

    async def ensure_running(self) -> bool:
        return await self._run(self._sync.ensure_running)

    async def start_app(
        self, mode: str = "adb_monkey", activity: Optional[str] = None
    ) -> None:
        return await self._run(
            functools.partial(self._sync.start_app, mode=mode, activity=activity)
        )

    async def stop_app(self) -> None:
        return await self._run(self._sync.stop_app)

    async def capture(self, method: str = "adb") -> bytes:
        return await self._run(self._sync.capture, method)

    async def capture_ndarray(self, method: str = "adb"):
        """异步截图，直接返回 BGR ndarray。"""
        return await self._run(self._sync.capture_ndarray, method)

    async def tap(self, x: int, y: int) -> None:
        return await self._run(self._sync.tap, x, y)

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300
    ) -> None:
        return await self._run(
            functools.partial(
                self._sync.swipe, x1, y1, x2, y2, dur_ms=dur_ms
            )
        )

    async def push_login_data(
        self, login_id: str, data_dir: str = "putonglogindata"
    ) -> bool:
        return await self._run(
            functools.partial(
                self._sync.push_login_data, login_id, data_dir=data_dir
            )
        )

    async def adb_is_app_running(self) -> bool:
        return await self._run(
            self._sync.adb.is_app_running,
            self._sync.cfg.adb_addr,
            self._sync.cfg.pkg_name,
        )

    async def adb_tap(self, x: int, y: int) -> None:
        await self._run(self._sync.adb.tap, self._sync.cfg.adb_addr, x, y)

    async def adb_shell(
        self, cmd: str, timeout: Optional[float] = None
    ) -> tuple[int, str]:
        if timeout is None:
            return await self._run(
                self._sync.adb.shell, self._sync.cfg.adb_addr, cmd
            )
        return await self._run(
            functools.partial(
                self._sync.adb.shell,
                self._sync.cfg.adb_addr,
                cmd,
                timeout=timeout,
            )
        )

    async def adb_force_stop(self, pkg: str) -> None:
        await self._run(self._sync.adb.force_stop, self._sync.cfg.adb_addr, pkg)

    async def adb_root(self) -> bool:
        return await self._run(self._sync.adb.root, self._sync.cfg.adb_addr)

    def foreground(self) -> bool:
        return self._sync.foreground()
