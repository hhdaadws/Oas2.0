"""
通用 UI 自动化工具函数

提供模板匹配和 OCR 两套操作工具：
- wait_for_template / click_template：基于模板匹配
- wait_for_text / click_text：基于 OCR 文字识别
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from ..vision.template import Match, match_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter


async def wait_for_template(
    adapter: EmulatorAdapter,
    capture_method: str,
    template: str,
    *,
    timeout: float = 8.0,
    interval: float = 1.0,
    threshold: float | None = None,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> Optional[Match]:
    """轮询截图直到模板出现。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        template: 模板图片路径
        timeout: 最大等待秒数
        interval: 轮询间隔
        threshold: 匹配阈值（None 使用默认 0.85）
        log: 日志对象
        label: 日志标签
        popup_handler: 可选的弹窗处理器（PopupHandler 实例）

    Returns:
        Match 对象，超时返回 None。
    """
    tag = f"[{label}] " if label else ""
    elapsed = 0.0
    kwargs = {"threshold": threshold} if threshold is not None else {}

    while elapsed < timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            m = match_template(screenshot, template, **kwargs)
            if m:
                if log:
                    log.info(f"{tag}检测到模板 (score={m.score:.3f}, elapsed={elapsed:.1f}s)")
                return m
            # 模板未找到时检查弹窗
            if popup_handler is not None:
                dismissed = await popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    continue  # 弹窗关闭后立即重试，不消耗 interval
        await asyncio.sleep(interval)
        elapsed += interval

    if log:
        log.warning(f"{tag}等待模板超时 ({timeout:.0f}s)")
    return None


async def click_template(
    adapter: EmulatorAdapter,
    capture_method: str,
    template: str,
    *,
    timeout: float = 8.0,
    interval: float = 1.0,
    settle: float = 0.5,
    post_delay: float = 1.5,
    verify_gone: bool = False,
    max_clicks: int = 3,
    gone_interval: float = 1.0,
    threshold: float | None = None,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> bool:
    """等待模板出现 → 稳定等待 → 点击 → 可选验证消失。

    流程:
        1. wait_for_template 等待模板出现
        2. sleep(settle) 让 UI 完全加载
        3. 重新截图确认模板仍在，获取最新坐标
        4. 点击模板中心
        5. 若 verify_gone=True：检查模板是否消失，仍在则重试

    Args:
        settle: 检测到模板后额外等待秒数，让 UI 完全加载
        post_delay: 点击后等待秒数，让 UI 过渡
        verify_gone: 点击后是否验证模板消失
        max_clicks: verify_gone 模式下最大点击次数
        gone_interval: 点击后到验证之间的等待秒数

    Returns:
        True 表示找到并点击成功，False 表示超时未找到。
    """
    tag = f"[{label}] " if label else ""
    addr = adapter.cfg.adb_addr
    kwargs = {"threshold": threshold} if threshold is not None else {}

    # 1) 等待模板出现
    m = await wait_for_template(
        adapter, capture_method, template,
        timeout=timeout, interval=interval,
        threshold=threshold, log=log, label=label,
        popup_handler=popup_handler,
    )
    if not m:
        return False

    # 2) settle 等待 UI 完全加载
    if settle > 0:
        await asyncio.sleep(settle)

    # 3-5) 点击（含重试逻辑）
    for attempt in range(max_clicks):
        # 重新截图获取最新坐标
        screenshot = adapter.capture(capture_method)
        if screenshot is None:
            if log:
                log.warning(f"{tag}截图失败 (attempt={attempt + 1})")
            await asyncio.sleep(gone_interval)
            continue

        m = match_template(screenshot, template, **kwargs)
        if not m:
            # 模板已经不在了（可能之前的操作已生效或 UI 发生变化）
            if log:
                log.info(f"{tag}模板已不在画面中")
            return True

        # 点击模板中心
        cx, cy = m.center
        adapter.adb.tap(addr, cx, cy)
        if log:
            log.info(f"{tag}点击 ({cx}, {cy}) (attempt={attempt + 1})")

        if not verify_gone:
            # 不需要验证，点完即可
            break

        # 等待 UI 响应后验证模板是否消失
        await asyncio.sleep(gone_interval)
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            still = match_template(screenshot, template, **kwargs)
            if not still:
                if log:
                    log.info(f"{tag}验证通过，模板已消失")
                break
            if log:
                log.info(f"{tag}模板仍在，将重试点击 ({attempt + 1}/{max_clicks})")
        # 继续重试
    else:
        if verify_gone and log:
            log.warning(f"{tag}已达最大点击次数 ({max_clicks})，模板可能仍在")

    # 点击后等待 UI 过渡
    if post_delay > 0:
        await asyncio.sleep(post_delay)

    return True


__all__ = ["wait_for_template", "click_template", "wait_for_text", "click_text"]


# ---------------------------------------------------------------------------
# OCR 辅助函数
# ---------------------------------------------------------------------------

from ..ocr import find_text as _find_text
from ..ocr.types import OcrBox


async def wait_for_text(
    adapter: EmulatorAdapter,
    capture_method: str,
    keyword: str,
    *,
    roi: tuple[int, int, int, int] | None = None,
    timeout: float = 8.0,
    interval: float = 1.0,
    min_confidence: float = 0.6,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> Optional[OcrBox]:
    """轮询截图直到 OCR 识别出包含 keyword 的文本。

    与 wait_for_template 对称的 API。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        keyword: 要查找的关键词
        roi: 可选区域 (x, y, w, h)，仅识别该区域
        timeout: 最大等待秒数
        interval: 轮询间隔
        min_confidence: 最低置信度阈值
        log: 日志对象
        label: 日志标签
        popup_handler: 可选的弹窗处理器（PopupHandler 实例）

    Returns:
        OcrBox 对象，超时返回 None。
    """
    tag = f"[{label}] " if label else ""
    elapsed = 0.0

    while elapsed < timeout:
        screenshot = adapter.capture(capture_method)
        if screenshot is not None:
            box = _find_text(
                screenshot, keyword,
                roi=roi, min_confidence=min_confidence,
            )
            if box:
                if log:
                    log.info(
                        f'{tag}OCR 检测到 "{keyword}"'
                        f" (confidence={box.confidence:.3f},"
                        f" elapsed={elapsed:.1f}s)"
                    )
                return box
            # 文本未找到时检查弹窗
            if popup_handler is not None:
                dismissed = await popup_handler.check_and_dismiss(screenshot)
                if dismissed > 0:
                    continue  # 弹窗关闭后立即重试
        await asyncio.sleep(interval)
        elapsed += interval

    if log:
        log.warning(f'{tag}OCR 等待 "{keyword}" 超时 ({timeout:.0f}s)')
    return None


async def click_text(
    adapter: EmulatorAdapter,
    capture_method: str,
    keyword: str,
    *,
    roi: tuple[int, int, int, int] | None = None,
    timeout: float = 8.0,
    interval: float = 1.0,
    settle: float = 0.5,
    post_delay: float = 1.5,
    min_confidence: float = 0.6,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> bool:
    """等待 OCR 识别出关键词 → 点击文本中心。

    与 click_template 对称的 API。

    Args:
        settle: 检测到文本后额外等待秒数
        post_delay: 点击后等待秒数
        其余参数同 wait_for_text

    Returns:
        True 表示找到并点击成功，False 表示超时未找到。
    """
    tag = f"[{label}] " if label else ""
    addr = adapter.cfg.adb_addr

    box = await wait_for_text(
        adapter, capture_method, keyword,
        roi=roi, timeout=timeout, interval=interval,
        min_confidence=min_confidence, log=log, label=label,
        popup_handler=popup_handler,
    )
    if not box:
        return False

    if settle > 0:
        await asyncio.sleep(settle)

    # 重新截图获取最新坐标
    screenshot = adapter.capture(capture_method)
    if screenshot is not None:
        fresh = _find_text(
            screenshot, keyword,
            roi=roi, min_confidence=min_confidence,
        )
        if fresh:
            box = fresh

    cx, cy = box.center
    adapter.adb.tap(addr, cx, cy)
    if log:
        log.info(f'{tag}OCR 点击 "{keyword}" ({cx}, {cy})')

    if post_delay > 0:
        await asyncio.sleep(post_delay)

    return True
