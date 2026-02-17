"""
异步 EmulatorAdapter 包装器

将同步的 EmulatorAdapter 方法通过 run_in_executor 转为异步方法，
使其在 asyncio 事件循环中不阻塞其他 Worker。

使用方式：
    adapter = EmulatorAdapter(cfg)
    async_adapter = AsyncEmulatorAdapter(adapter)
    screenshot = await async_adapter.capture()  # 不阻塞事件循环
"""
from __future__ import annotations

import functools
from typing import Optional

from ...core.thread_pool import run_in_io
from .adapter import EmulatorAdapter, AdapterConfig


class AsyncEmulatorAdapter:
    """EmulatorAdapter 的异步包装器（代理模式）。

    所有 I/O 阻塞方法通过 run_in_io offload 到线程池执行，
    释放 asyncio 事件循环给其他 Worker。
    """

    def __init__(self, adapter: EmulatorAdapter) -> None:
        self._sync = adapter

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

    async def ensure_running(self) -> bool:
        return await run_in_io(self._sync.ensure_running)

    async def start_app(
        self, mode: str = "adb_monkey", activity: Optional[str] = None
    ) -> None:
        return await run_in_io(
            functools.partial(self._sync.start_app, mode=mode, activity=activity)
        )

    async def stop_app(self) -> None:
        return await run_in_io(self._sync.stop_app)

    async def capture(self, method: str = "adb") -> bytes:
        return await run_in_io(self._sync.capture, method)

    async def capture_ndarray(self, method: str = "adb"):
        """异步截图，直接返回 BGR ndarray。"""
        return await run_in_io(self._sync.capture_ndarray, method)

    async def tap(self, x: int, y: int) -> None:
        return await run_in_io(self._sync.tap, x, y)

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300
    ) -> None:
        return await run_in_io(
            functools.partial(
                self._sync.swipe, x1, y1, x2, y2, dur_ms=dur_ms
            )
        )

    async def push_login_data(
        self, login_id: str, data_dir: str = "putonglogindata"
    ) -> bool:
        return await run_in_io(
            functools.partial(
                self._sync.push_login_data, login_id, data_dir=data_dir
            )
        )

    def foreground(self) -> bool:
        return self._sync.foreground()
