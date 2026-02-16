"""
通用式神觉醒模块

提供可复用的觉醒流程函数，适用于任何需要觉醒式神的场景。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .helpers import click_template, wait_for_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# 觉醒相关模板
_TPL_JUEXING = "assets/ui/templates/shishen_juexing.png"
_TPL_SHISHENJUEXING = "assets/ui/templates/shishen_shishenjuexing.png"


async def awaken_shikigami(
    adapter: EmulatorAdapter,
    capture_method: str,
    *,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> bool:
    """通用式神觉醒流程（在式神详情页内调用）。

    前置条件：已进入目标式神的详情页面。

    流程:
        1. 点击坐标 (935, 269)（觉醒入口按钮）
        2. 等待并点击 shishen_juexing.png（觉醒按钮）
        3. 点击 shishen_shishenjuexing.png（确认觉醒）

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式
        log: 日志对象
        label: 日志标签
        popup_handler: 弹窗处理器

    Returns:
        True 觉醒成功，False 失败
    """
    tag = f"[{label}] " if label else ""
    addr = adapter.cfg.adb_addr

    # 1. 点击觉醒入口坐标
    adapter.adb.tap(addr, 935, 269)
    if log:
        log.info(f"{tag}点击觉醒入口 (935, 269)")
    await asyncio.sleep(1.5)

    # 2. 等待并点击觉醒按钮
    clicked = await click_template(
        adapter, capture_method, _TPL_JUEXING,
        timeout=8.0, settle=0.5, post_delay=1.0,
        log=log, label=f"{label}觉醒按钮" if label else "觉醒按钮",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag}未找到觉醒按钮")
        return False

    # 3. 点击确认觉醒
    clicked = await click_template(
        adapter, capture_method, _TPL_SHISHENJUEXING,
        timeout=8.0, settle=0.5, post_delay=2.0,
        log=log, label=f"{label}确认觉醒" if label else "确认觉醒",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag}未找到确认觉醒按钮")
        return False

    if log:
        log.info(f"{tag}觉醒操作完成")
    return True
