"""
全局线程池管理

提供统一的 ThreadPoolExecutor 实例，供 AsyncEmulatorAdapter 和其他
需要将阻塞操作 offload 到线程的模块使用。

- I/O 池：ADB subprocess、同步 DB 操作等 I/O 密集操作
- 计算池：OpenCV 模板匹配、OCR 等 CPU 密集操作
"""
from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from .config import settings
from .logger import logger

_io_pool: Optional[ThreadPoolExecutor] = None
_compute_pool: Optional[ThreadPoolExecutor] = None
_emu_io_pools: Dict[str, ThreadPoolExecutor] = {}
_emu_io_inflight: Dict[str, int] = {}
_emu_io_lock = threading.Lock()


def _auto_io_pool_size() -> int:
    """根据模拟器数量自动计算 I/O 线程池大小。

    规则: max(8, emulator_count * 2 + 4)，上限 32。
    """
    try:
        from ..db import SessionLocal
        from ..db.models import Emulator
        with SessionLocal() as db:
            count = db.query(Emulator).count()
        return min(max(8, count * 2 + 4), 32)
    except Exception:
        return 24


def _auto_compute_pool_size() -> int:
    """根据 CPU 核数自动计算计算线程池大小。

    规则: max(4, cpu_count // 2)，上限 24。
    """
    cpu = os.cpu_count() or 4
    return min(max(4, cpu // 2), 24)


def get_io_pool() -> ThreadPoolExecutor:
    """获取 I/O 线程池（ADB subprocess 调用、同步 DB 操作等）。"""
    global _io_pool
    if _io_pool is None:
        size = settings.io_thread_pool_size
        if size <= 0:
            size = _auto_io_pool_size()
        _io_pool = ThreadPoolExecutor(
            max_workers=size,
            thread_name_prefix="adb-io",
        )
        logger.info("I/O 线程池已创建: max_workers={}", size)
    return _io_pool


def get_compute_pool() -> ThreadPoolExecutor:
    """获取计算线程池（OpenCV 模板匹配、OCR 等）。"""
    global _compute_pool
    if _compute_pool is None:
        size = settings.compute_thread_pool_size
        if size <= 0:
            size = _auto_compute_pool_size()
        _compute_pool = ThreadPoolExecutor(
            max_workers=size,
            thread_name_prefix="cv-compute",
        )
        logger.info("计算线程池已创建: max_workers={}", size)
    return _compute_pool


def get_emulator_io_pool(io_key: str) -> ThreadPoolExecutor:
    """获取指定模拟器的单线程 I/O 池。"""
    key = str(io_key or "").strip()
    if not key:
        return get_io_pool()

    with _emu_io_lock:
        pool = _emu_io_pools.get(key)
        if pool is None:
            index = len(_emu_io_pools) + 1
            pool = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"emu-io-{index}",
            )
            _emu_io_pools[key] = pool
            logger.info("模拟器 I/O 线程池已创建: io_key={}", key)
        return pool


async def run_in_io(func, *args):
    """在 I/O 线程池中执行同步函数并 await 结果。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_io_pool(), func, *args)


async def run_in_emulator_io(io_key: str, func, *args):
    """在指定模拟器单线程 I/O 池中执行同步函数并 await 结果。"""
    key = str(io_key or "").strip()
    if not key:
        return await run_in_io(func, *args)

    loop = asyncio.get_running_loop()
    pool = get_emulator_io_pool(key)

    with _emu_io_lock:
        _emu_io_inflight[key] = _emu_io_inflight.get(key, 0) + 1

    try:
        return await loop.run_in_executor(pool, func, *args)
    finally:
        with _emu_io_lock:
            current = _emu_io_inflight.get(key, 0)
            if current <= 1:
                _emu_io_inflight.pop(key, None)
            else:
                _emu_io_inflight[key] = current - 1


async def run_in_compute(func, *args):
    """在计算线程池中执行同步函数并 await 结果。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_compute_pool(), func, *args)


async def run_in_db(func, *args):
    """在 I/O 线程池中执行同步 DB 操作并 await 结果。

    语义别名：与 run_in_io 使用同一线程池，
    但命名上区分用途，便于未来独立优化。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_io_pool(), func, *args)


def emulator_io_pool_stats() -> dict:
    """返回模拟器 I/O 池统计。"""
    with _emu_io_lock:
        return {
            "pool_count": len(_emu_io_pools),
            "active_keys": len(_emu_io_inflight),
        }


def shutdown_pools() -> None:
    """关闭所有线程池（在 app shutdown 时调用）。"""
    global _io_pool, _compute_pool
    if _io_pool:
        _io_pool.shutdown(wait=False)
        _io_pool = None
    if _compute_pool:
        _compute_pool.shutdown(wait=False)
        _compute_pool = None
    with _emu_io_lock:
        for pool in _emu_io_pools.values():
            pool.shutdown(wait=False)
        _emu_io_pools.clear()
        _emu_io_inflight.clear()
    logger.info("线程池已关闭")
