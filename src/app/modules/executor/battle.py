"""
通用战斗模块

处理战斗确认、等待战斗结束、判定胜负、领取奖励。
可被地鬼、探索、逢魔等多个执行器复用。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from ..vision.template import Match, match_template
from .helpers import click_template, wait_for_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# 模板路径
_TPL_ZHUNBEI = "assets/ui/templates/zhandou_zhunbei.png"
_TPL_SHENGLI = "assets/ui/templates/zhandou_shengli.png"
_TPL_JIANGLI = "assets/ui/templates/zhandou_jiangli.png"


def _discover_zidong_templates() -> List[str]:
    """自动发现 zhandou_zidong_*.png 系列模板。"""
    paths = sorted(Path("assets/ui/templates").glob("zhandou_zidong_*.png"))
    return [p.as_posix() for p in paths]


_TPL_ZIDONG_LIST = _discover_zidong_templates()

# 战斗结果常量
VICTORY = "victory"
DEFEAT = "defeat"
TIMEOUT = "timeout"
ERROR = "error"


async def _wait_for_any_template(
    adapter: EmulatorAdapter,
    capture_method: str,
    templates: List[str],
    *,
    timeout: float = 8.0,
    interval: float = 1.0,
    threshold: float | None = None,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> Optional[Match]:
    """轮询截图直到任一模板出现。

    Args:
        templates: 模板路径列表，任一匹配即返回。

    Returns:
        Match 对象，超时返回 None。
    """
    tag = f"[{label}] " if label else ""
    elapsed = 0.0
    kwargs = {"threshold": threshold} if threshold is not None else {}

    while elapsed < timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            for tpl in templates:
                m = match_template(screenshot, tpl, **kwargs)
                if m:
                    if log:
                        log.info(
                            f"{tag}检测到模板 {Path(tpl).name}"
                            f" (score={m.score:.3f}, elapsed={elapsed:.1f}s)"
                        )
                    return m
            # 模板未找到时检查弹窗
            if popup_handler is not None:
                dismissed = await popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    continue
        await asyncio.sleep(interval)
        elapsed += interval

    if log:
        log.warning(f"{tag}等待模板超时 ({timeout:.0f}s)")
    return None


async def run_battle(
    adapter: EmulatorAdapter,
    capture_method: str,
    *,
    confirm_template: str | None = None,
    battle_timeout: float = 120.0,
    log: Any = None,
    popup_handler: Any = None,
) -> str:
    """执行一场完整战斗并返回结果。

    从确认按钮出现时接管，处理整个战斗流程直到奖励领取完毕。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        confirm_template: 战斗确认按钮模板路径（如 digui_tiaozhan_sure.png），
                          为 None 则跳过确认步骤
        battle_timeout: 战斗阶段最大等待秒数
        log: 日志对象
        popup_handler: 弹窗处理器

    Returns:
        "victory" | "defeat" | "timeout" | "error"
    """
    tag = "[战斗]"

    # 1. 点击确认按钮（如 digui_tiaozhan_sure.png）
    if confirm_template:
        clicked = await click_template(
            adapter, capture_method, confirm_template,
            timeout=8.0, settle=0.5, post_delay=1.5,
            log=log, label="战斗-确认",
            popup_handler=popup_handler,
        )
        if not clicked:
            if log:
                log.error(f"{tag} 未检测到确认按钮")
            return ERROR

    # 2+3. 点击准备并等待进入战斗（自动按钮出现）
    #      准备按钮点击可能失败，循环重试直到准备消失且自动出现
    battle_entered = False
    enter_elapsed = 0.0
    enter_timeout = 20.0
    enter_interval = 1.5

    while enter_elapsed < enter_timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            await asyncio.sleep(enter_interval)
            enter_elapsed += enter_interval
            continue

        # 优先检查是否已进入战斗（自动按钮出现）
        for tpl in _TPL_ZIDONG_LIST:
            m = match_template(screenshot, tpl)
            if m:
                if log:
                    log.info(
                        f"{tag} 检测到自动按钮 {Path(tpl).name}，已进入战斗"
                        f" (elapsed={enter_elapsed:.1f}s)"
                    )
                battle_entered = True
                break
        if battle_entered:
            break

        # 检查弹窗
        if popup_handler is not None:
            dismissed = await popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0:
                continue

        # 准备按钮仍在则再次点击
        m_zhunbei = match_template(screenshot, _TPL_ZHUNBEI)
        if m_zhunbei:
            cx, cy = m_zhunbei.center
            if log:
                log.info(f"{tag} 检测到准备按钮，点击 ({cx}, {cy})")
            adapter.adb.tap(adapter.cfg.adb_addr, cx, cy)

        await asyncio.sleep(enter_interval)
        enter_elapsed += enter_interval

    if not battle_entered:
        if log:
            log.error(f"{tag} 未检测到战斗界面 (准备/自动超时)")
        return ERROR

    if log:
        log.info(f"{tag} 已进入战斗，等待战斗结束 (timeout={battle_timeout}s)")

    # 4. 轮询等待战斗结束（胜利）
    shengli = await wait_for_template(
        adapter, capture_method, _TPL_SHENGLI,
        timeout=battle_timeout, interval=2.0,
        log=log, label="战斗-胜利",
        popup_handler=popup_handler,
    )
    if not shengli:
        if log:
            log.warning(f"{tag} 等待战斗结果超时")
        return TIMEOUT

    # 5. 点击胜利
    if log:
        log.info(f"{tag} 战斗胜利，点击")
    clicked = await click_template(
        adapter, capture_method, _TPL_SHENGLI,
        timeout=5.0, settle=0.5, post_delay=1.5,
        log=log, label="战斗-点击胜利",
        popup_handler=popup_handler,
    )

    # 6. 等待并点击奖励
    clicked = await click_template(
        adapter, capture_method, _TPL_JIANGLI,
        timeout=8.0, settle=0.5, post_delay=1.5,
        log=log, label="战斗-奖励",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag} 未检测到奖励界面，但战斗已胜利")

    if log:
        log.info(f"{tag} 战斗流程完成")
    return VICTORY


__all__ = ["run_battle", "VICTORY", "DEFEAT", "TIMEOUT", "ERROR"]
