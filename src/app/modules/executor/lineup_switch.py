"""
通用阵容切换函数

在式神界面中切换到指定的分组和阵容预设。
可被地鬼、逢魔、探索、道馆等多个执行器复用。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..vision.grid_detect import (
    detect_right_column_cells, find_template_in_grid,
    RIGHT_COL_X_START, RIGHT_COL_X_END, RIGHT_COL_Y_START, RIGHT_COL_Y_END,
    GRID_ROI,
)
from ..vision.template import match_template
from .helpers import click_template, wait_for_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter
    from ..ui.manager import UIManager

# 模板路径
_TPL_SHISHEN_TAG = "assets/ui/templates/tag_shishen_1.png"
_TPL_SHISHEN_TIHUAN = "assets/ui/templates/shishen_tihuan.png"
_TPL_SHISHEN_QUEDING = "assets/ui/templates/shishen_queding.png"


async def switch_lineup(
    adapter: EmulatorAdapter,
    ui: UIManager,
    capture_method: str,
    group: int,
    position: int,
    log: Any = None,
) -> bool:
    """切换到指定的分组和阵容预设。

    流程:
        1. 导航到式神界面
        2. 点击式神标签进入阵容视图
        3. 识别右侧分组列，点击目标分组
        4. 识别左侧阵容行，点击目标阵容
        5. 点击确定完成切换

    Args:
        adapter: 模拟器适配器
        ui: UIManager 实例
        capture_method: 截图方式 ("adb" / "ipc")
        group: 目标分组编号 (1-indexed)
        position: 目标阵容编号 (1-indexed)
        log: 日志对象

    Returns:
        True 表示切换成功，False 表示失败。
    """
    tag = "[阵容切换]"
    addr = adapter.cfg.adb_addr

    # 1. 导航到式神界面
    if log:
        log.info(f"{tag} 导航到式神界面")
    in_shishen = await ui.ensure_ui("SHISHEN", max_steps=6, step_timeout=3.0)
    if not in_shishen:
        if log:
            log.error(f"{tag} 导航到式神界面失败")
        return False

    await asyncio.sleep(1.0)

    # 2. 点击式神标签，进入阵容替换视图
    if log:
        log.info(f"{tag} 点击式神标签")
    clicked = await click_template(
        adapter, capture_method, _TPL_SHISHEN_TAG,
        timeout=5.0, settle=0.5, post_delay=1.5,
        log=log, label="阵容切换-标签",
        popup_handler=ui.popup_handler,
    )
    if not clicked:
        if log:
            log.error(f"{tag} 未检测到式神标签")
        return False

    # 3. 等待替换界面出现（shishen_tihuan.png 可见）
    tihuan = await wait_for_template(
        adapter, capture_method, _TPL_SHISHEN_TIHUAN,
        timeout=5.0, interval=0.5,
        log=log, label="阵容切换-等待替换界面",
        popup_handler=ui.popup_handler,
    )
    if not tihuan:
        if log:
            log.error(f"{tag} 未检测到替换界面 (shishen_tihuan)")
        return False

    # 4. 截图识别右侧分组列
    screenshot = adapter.capture(capture_method)
    if screenshot is None:
        if log:
            log.error(f"{tag} 截图失败")
        return False

    cells = detect_right_column_cells(screenshot)
    if not cells:
        if log:
            log.error(f"{tag} 未检测到右侧分组列")
        return False

    # 5. 从上往下划分组列，回到顶部
    swipe_x = (RIGHT_COL_X_START + RIGHT_COL_X_END) // 2
    adapter.swipe(swipe_x, RIGHT_COL_Y_START + 50, swipe_x, RIGHT_COL_Y_END - 50, dur_ms=500)
    await asyncio.sleep(0.8)

    # 重新截图检测分组
    screenshot = adapter.capture(capture_method)
    if screenshot is None:
        if log:
            log.error(f"{tag} 上划后截图失败")
        return False
    cells = detect_right_column_cells(screenshot)
    if not cells:
        if log:
            log.error(f"{tag} 上划后未检测到分组")
        return False

    if group < 1 or group > len(cells):
        if log:
            log.error(f"{tag} 分组编号 {group} 超出范围 (共 {len(cells)} 个分组)")
        return False

    # 6. 点击目标分组
    target_cell = cells[group - 1]  # 1-indexed → 0-indexed
    cx, cy = target_cell.center
    if log:
        log.info(f"{tag} 点击分组 {group}: ({cx}, {cy})")
    adapter.adb.tap(addr, cx, cy)
    await asyncio.sleep(1.5)

    # 7. 截图识别左侧阵容行
    screenshot = adapter.capture(capture_method)
    if screenshot is None:
        if log:
            log.error(f"{tag} 截图失败（分组点击后）")
        return False

    positions = find_template_in_grid(screenshot, _TPL_SHISHEN_TIHUAN, threshold=0.80)
    if not positions:
        if log:
            log.error(f"{tag} 未检测到阵容行")
        return False

    # 8. 从上往下划阵容列，回到顶部
    grid_cx = GRID_ROI[0] + GRID_ROI[2] // 2
    grid_top = GRID_ROI[1]
    grid_bottom = GRID_ROI[1] + GRID_ROI[3]
    adapter.swipe(grid_cx, grid_top + 30, grid_cx, grid_bottom - 30, dur_ms=500)
    await asyncio.sleep(0.8)

    # 重新截图检测阵容行
    screenshot = adapter.capture(capture_method)
    if screenshot is None:
        if log:
            log.error(f"{tag} 上划后截图失败")
        return False
    positions = find_template_in_grid(screenshot, _TPL_SHISHEN_TIHUAN, threshold=0.80)
    if not positions:
        if log:
            log.error(f"{tag} 上划后未检测到阵容行")
        return False

    if position < 1 or position > len(positions):
        if log:
            log.error(f"{tag} 阵容编号 {position} 超出范围 (共 {len(positions)} 个阵容)")
        return False

    # 9. 点击目标阵容
    target_pos = positions[position - 1]  # 1-indexed → 0-indexed
    px, py = target_pos.center
    if log:
        log.info(f"{tag} 点击阵容 {position} (行 {target_pos.row}): ({px}, {py})")
    adapter.adb.tap(addr, px, py)
    await asyncio.sleep(1.5)

    # 10. 点击确定（如果未出现确定按钮，说明当前阵容已是目标阵容，无需切换）
    confirmed = await click_template(
        adapter, capture_method, _TPL_SHISHEN_QUEDING,
        timeout=5.0, settle=0.5, post_delay=1.5,
        verify_gone=True,
        log=log, label="阵容切换-确定",
        popup_handler=ui.popup_handler,
    )
    if not confirmed:
        if log:
            log.info(f"{tag} 未检测到确定按钮，当前阵容已是目标阵容，无需切换")
        return True

    if log:
        log.info(f"{tag} 阵容切换完成: 分组={group}, 阵容={position}")
    return True


__all__ = ["switch_lineup"]
