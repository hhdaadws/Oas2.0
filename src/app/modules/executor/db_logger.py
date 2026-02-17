"""
数据库日志写入工具（非阻塞）。
将任务执行关键事件写入 logs 表，供仪表盘"系统日志"面板展示。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Log

_log = logger.bind(module="db_logger")


def _write_log_sync(
    account_id: int,
    type_: str,
    level: str,
    message: str,
) -> None:
    try:
        with SessionLocal() as db:
            entry = Log(
                account_id=account_id,
                type=type_,
                level=level,
                message=message,
                ts=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
    except Exception as exc:
        _log.warning(f"写入数据库日志失败: {exc}")


def emit(
    account_id: int,
    message: str,
    *,
    type_: str = "task",
    level: str = "INFO",
) -> None:
    """非阻塞地写入一条数据库日志。

    通过 run_in_executor 提交到线程池，不阻塞事件循环，不 await 结果。
    """
    try:
        loop = asyncio.get_running_loop()
        from ...core.thread_pool import get_io_pool
        loop.run_in_executor(get_io_pool(), _write_log_sync, account_id, type_, level, message)
    except RuntimeError:
        _write_log_sync(account_id, type_, level, message)
