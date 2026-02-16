"""
签到 UI 操作：
- 已在签到界面 → 日常 → 一键完成
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter

# 模板路径
_QIANDAO_RICHANG = "assets/ui/templates/qiandao_richang.png"
_QIANDAO_YIJIANWANCHENG = "assets/ui/templates/qiandao_yijianwancheng.png"
_LINGQU_CHENGGONG = "assets/ui/templates/lingquchenggong.png"
_EXIT = "assets/ui/templates/exit.png"


async def perform_signin(
    adapter: EmulatorAdapter,
    capture_method: str = "adb",
    *,
    log: Any = None,
    popup_handler: Any = None,
) -> bool:
    """在签到界面中执行签到操作（调用前需已通过 ensure_ui 导航到签到界面）。

    流程：点击 qiandao_richang.png → 点击 qiandao_yijianwancheng.png。
    返回 True 表示签到完成，False 表示某一步失败。
    """
    from ..executor.helpers import click_template

    label = "签到"

    # Step 1: 点击日常签到 (qiandao_richang.png) — 可选步骤
    # 进入签到界面后有概率已处于可一键完成状态，此步骤找不到时继续
    ok = await click_template(
        adapter, capture_method, _QIANDAO_RICHANG,
        timeout=5.0, post_delay=1.5,
        log=log, label=label, popup_handler=popup_handler,
    )
    if not ok:
        if log:
            log.info("[签到] 未检测到日常签到按钮，尝试直接点击一键完成")

    # Step 2: 点击一键完成 (qiandao_yijianwancheng.png)
    ok = await click_template(
        adapter, capture_method, _QIANDAO_YIJIANWANCHENG,
        timeout=8.0, post_delay=1.5,
        log=log, label=label, popup_handler=popup_handler,
    )
    if not ok:
        if log:
            log.warning("[签到] 未检测到一键完成按钮 (qiandao_yijianwancheng.png)")
        return False

    # Step 3: 关闭领取成功弹窗 (lingquchenggong.png)
    ok = await click_template(
        adapter, capture_method, _LINGQU_CHENGGONG,
        timeout=5.0, post_delay=1.0,
        verify_gone=True, max_clicks=3, gone_interval=1.0,
        log=log, label=label, popup_handler=popup_handler,
    )
    if not ok:
        if log:
            log.warning("[签到] 未检测到领取成功弹窗")

    # Step 4: 处理可能出现的 exit.png 关闭按钮（可选步骤）
    await click_template(
        adapter, capture_method, _EXIT,
        timeout=3.0, post_delay=1.0,
        log=log, label=label, popup_handler=popup_handler,
    )

    # Step 5: 清理可能残留的弹窗
    # 修复：lingquchenggong 被 exit 遮挡导致 verify_gone 误判，
    # 点击 exit 后 lingquchenggong 重新出现的问题
    if popup_handler is not None:
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            dismissed = await popup_handler.check_and_dismiss(screenshot)
            if dismissed > 0 and log:
                log.info(f"[{label}] 清理了 {dismissed} 个残留弹窗")

    if log:
        log.info("[签到] 签到流程完成")
    return True


__all__ = [
    "perform_signin",
]
