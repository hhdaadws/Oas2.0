"""
通用 UI 自动化工具函数

提供模板匹配和 OCR 两套操作工具：
- wait_for_template / click_template：基于模板匹配
- wait_for_text / click_text：基于 OCR 文字识别
"""
from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Optional, Union

from ..vision.template import Match, match_template

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter
    from ..emu.async_adapter import AsyncEmulatorAdapter


async def _adapter_capture(adapter: "Union[EmulatorAdapter, AsyncEmulatorAdapter]", method: str):
    """兼容同步/异步 adapter 的截图，直接返回 BGR ndarray。"""
    result = adapter.capture_ndarray(method)
    if inspect.isawaitable(result):
        return await result
    return result


async def _adapter_tap(adapter: "Union[EmulatorAdapter, AsyncEmulatorAdapter]", x: int, y: int) -> None:
    """兼容同步/异步 adapter 的 adb tap。"""
    from ..emu.async_adapter import AsyncEmulatorAdapter
    if isinstance(adapter, AsyncEmulatorAdapter):
        await adapter.tap(x, y)
    else:
        adapter.adb.tap(adapter.cfg.adb_addr, x, y)


async def _adapter_swipe(
    adapter: "Union[EmulatorAdapter, AsyncEmulatorAdapter]",
    x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300,
) -> None:
    """兼容同步/异步 adapter 的 swipe。"""
    from ..emu.async_adapter import AsyncEmulatorAdapter
    if isinstance(adapter, AsyncEmulatorAdapter):
        await adapter.swipe(x1, y1, x2, y2, dur_ms)
    else:
        adapter.swipe(x1, y1, x2, y2, dur_ms)


async def wait_for_template(
    adapter: EmulatorAdapter,
    capture_method: str,
    template: str | list[str],
    *,
    timeout: float = 8.0,
    interval: float = 0.5,
    threshold: float | None = None,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> Optional[Match]:
    """轮询截图直到模板出现。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        template: 模板图片路径，或多个候选模板路径列表（任一匹配即返回）
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
    templates = [template] if isinstance(template, str) else template

    while elapsed < timeout:
        screenshot = await _adapter_capture(adapter, capture_method)
        if screenshot is not None:
            for tpl in templates:
                m = match_template(screenshot, tpl, **kwargs)
                if m:
                    if log:
                        log.info(f"{tag}检测到模板 {tpl} (score={m.score:.3f}, elapsed={elapsed:.1f}s)")
                    return m
            # 所有模板都未匹配时检查弹窗
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
    interval: float = 0.5,
    settle: float = 0.3,
    post_delay: float = 0.8,
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
        screenshot = await _adapter_capture(adapter, capture_method)
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

        # 点击模板区域内随机位置
        cx, cy = m.random_point()
        await _adapter_tap(adapter, cx, cy)
        if log:
            log.info(f"{tag}点击 ({cx}, {cy}) (attempt={attempt + 1})")

        if not verify_gone:
            # 不需要验证，点完即可
            break

        # 等待 UI 响应后验证模板是否消失
        await asyncio.sleep(gone_interval)
        screenshot = await _adapter_capture(adapter, capture_method)
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


__all__ = [
    "wait_for_template", "click_template", "wait_for_text", "click_text",
    "wait_for_qrcode",
    "check_and_handle_liao_not_joined", "check_and_create_jiejie",
]


# ---------------------------------------------------------------------------
# 二维码等待
# ---------------------------------------------------------------------------

from ..vision.qrcode_detect import detect_qrcode as _detect_qrcode


async def wait_for_qrcode(
    adapter: "EmulatorAdapter",
    capture_method: str,
    *,
    timeout: float = 15.0,
    interval: float = 0.5,
    log: Any = None,
    label: str = "",
) -> bool:
    """轮询截图直到检测到二维码出现。

    Args:
        adapter: 模拟器适配器
        capture_method: 截图方式 ("adb" / "ipc")
        timeout: 最大等待秒数
        interval: 轮询间隔
        log: 日志对象
        label: 日志标签

    Returns:
        True 表示检测到二维码，False 表示超时未检测到。
    """
    tag = f"[{label}] " if label else ""
    elapsed = 0.0

    while elapsed < timeout:
        screenshot = await _adapter_capture(adapter, capture_method)
        if screenshot is not None and _detect_qrcode(screenshot):
            if log:
                log.info(f"{tag}检测到二维码 (elapsed={elapsed:.1f}s)")
            return True
        await asyncio.sleep(interval)
        elapsed += interval

    if log:
        log.warning(f"{tag}等待二维码超时 ({timeout:.0f}s)")
    return False


# ---------------------------------------------------------------------------
# OCR 辅助函数
# ---------------------------------------------------------------------------

from ..ocr import async_find_text as _async_find_text
from ..ocr.types import OcrBox


async def wait_for_text(
    adapter: EmulatorAdapter,
    capture_method: str,
    keyword: str,
    *,
    roi: tuple[int, int, int, int] | None = None,
    timeout: float = 8.0,
    interval: float = 0.5,
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
        screenshot = await _adapter_capture(adapter, capture_method)
        if screenshot is not None:
            box = await _async_find_text(
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
    interval: float = 0.5,
    settle: float = 0.3,
    post_delay: float = 0.8,
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
    screenshot = await _adapter_capture(adapter, capture_method)
    if screenshot is not None:
        fresh = await _async_find_text(
            screenshot, keyword,
            roi=roi, min_confidence=min_confidence,
        )
        if fresh:
            box = fresh

    cx, cy = box.random_point()
    await _adapter_tap(adapter, cx, cy)
    if log:
        log.info(f'{tag}OCR 点击 "{keyword}" ({cx}, {cy})')

    if post_delay > 0:
        await asyncio.sleep(post_delay)

    return True


# ---------------------------------------------------------------------------
# 寮未加入检测
# ---------------------------------------------------------------------------

_TPL_LIAO_YIJIANSHENQING = "assets/ui/templates/liao_yijianshenqing.png"
_TPL_LIAO_QUEDING = "assets/ui/templates/liao_queding.png"

# 延后时间（小时）
_LIAO_NOT_JOINED_DELAY_HOURS = 6


async def check_and_handle_liao_not_joined(
    adapter: "EmulatorAdapter",
    capture_method: str,
    account_id: int,
    *,
    log: Any = None,
    label: str = "",
) -> bool:
    """检测当前账号是否未加入寮，若是则执行一键申请并延后所有寮任务。

    应在 ensure_ui("LIAO") 或 ensure_ui("LIAO_SHANGDIAN") 返回 False 后调用。

    流程:
        1. 截图检测 liao_yijianshenqing.png（一键申请按钮）
        2. 若检测到，点击一键申请
        3. 等待并点击 liao_queding.png（确认按钮）
        4. 延后该账号所有寮相关任务的 next_time（6小时后）

    Returns:
        True 表示检测到未加入寮并已处理，False 表示不是未加入寮的情况。
    """
    tag = f"[{label}] " if label else ""

    screenshot = await _adapter_capture(adapter, capture_method)
    if screenshot is None:
        return False

    m = match_template(screenshot, _TPL_LIAO_YIJIANSHENQING)
    if not m:
        return False

    if log:
        log.warning(f"{tag}检测到一键申请界面(score={m.score:.2f})，账号未加入寮")

    # 1. 点击一键申请
    cx, cy = m.random_point()
    await _adapter_tap(adapter, cx, cy)
    if log:
        log.info(f"{tag}点击一键申请 ({cx}, {cy})")
    await asyncio.sleep(1.5)

    # 2. 点击确认
    ok = await click_template(
        adapter, capture_method, _TPL_LIAO_QUEDING,
        timeout=5.0, interval=0.5,
        settle=0.3, post_delay=1.0,
        log=log, label=f"{label}寮申请确认" if label else "寮申请确认",
    )
    if not ok and log:
        log.warning(f"{tag}未检测到确认按钮，申请可能未提交")

    # 3. 延后所有寮相关任务（offload 到线程池）
    await _defer_all_liao_tasks(account_id, _LIAO_NOT_JOINED_DELAY_HOURS, log=log, label=label)

    return True


async def _defer_all_liao_tasks(
    account_id: int,
    delay_hours: int,
    *,
    log: Any = None,
    label: str = "",
) -> None:
    """延后指定账号所有寮相关任务的 next_time（offload 到线程池）。"""
    from datetime import timedelta

    from sqlalchemy.orm.attributes import flag_modified

    from ...core.thread_pool import run_in_db
    from ...core.timeutils import format_beijing_time, now_beijing
    from ...db.base import SessionLocal
    from ...db.models import GameAccount

    tag = f"[{label}] " if label else ""
    bj_now = now_beijing()
    new_next_time = format_beijing_time(bj_now + timedelta(hours=delay_hours))

    liao_config_keys = ["领取寮金币", "寮商店"]

    def _do_defer():
        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if not account:
                    return
                cfg = account.task_config or {}
                for key in liao_config_keys:
                    task_cfg = cfg.get(key, {})
                    task_cfg["next_time"] = new_next_time
                    cfg[key] = task_cfg
                    if log:
                        log.info(f"{tag}{key} next_time 延后至 {new_next_time} (未加入寮)")
                account.task_config = cfg
                flag_modified(account, "task_config")
                db.commit()
        except Exception as e:
            if log:
                log.error(f"{tag}延后寮任务 next_time 失败: {e}")

    await run_in_db(_do_defer)


# ---------------------------------------------------------------------------
# 结界创建检测
# ---------------------------------------------------------------------------

_TPL_JIEJIE = "assets/ui/templates/jiejie.png"
_TPL_CHUANGJIAN_JIEJIE = "assets/ui/templates/chuangjianjiejie.png"
_TPL_BACK = "assets/ui/templates/back.png"


async def check_and_create_jiejie(
    adapter: "EmulatorAdapter",
    capture_method: str,
    *,
    log: Any = None,
    label: str = "",
    popup_handler: Any = None,
) -> bool:
    """在寮界面内检测并创建结界（如果尚未创建）。

    前置条件: 调用者已导航到 LIAO 界面。
    后置保证: 无论是否创建，都会返回到寮界面。

    流程:
        1. 点击 jiejie.png（结界按钮）进入结界子页面
        2. 检测 chuangjianjiejie.png（创建结界按钮）
           - 出现 → 点击创建 → 点击 back 返回寮界面 → 返回 True
           - 未出现 → 结界已存在，点击 back 返回寮界面 → 返回 False

    Returns:
        True 表示成功创建了结界，False 表示结界已存在（无需创建）。
    """
    tag = f"[{label}] " if label else ""

    # 1. 点击结界按钮进入结界子页面
    clicked = await click_template(
        adapter, capture_method, _TPL_JIEJIE,
        timeout=8.0, settle=0.5, post_delay=2.0,
        log=log, label=f"{label}结界按钮" if label else "结界按钮",
        popup_handler=popup_handler,
    )
    if not clicked:
        if log:
            log.warning(f"{tag}未找到结界按钮")
        return False

    # 2. 检测创建结界按钮
    create_match = await wait_for_template(
        adapter, capture_method, _TPL_CHUANGJIAN_JIEJIE,
        timeout=5.0, interval=0.5,
        log=log, label=f"{label}创建结界" if label else "创建结界",
        popup_handler=popup_handler,
    )

    if create_match:
        # 结界未创建，点击创建
        cx, cy = create_match.random_point()
        await _adapter_tap(adapter, cx, cy)
        if log:
            log.info(f"{tag}点击创建结界 ({cx}, {cy})")
        await asyncio.sleep(2.0)

        # 返回寮界面
        await click_template(
            adapter, capture_method, _TPL_BACK,
            timeout=5.0, settle=0.3, post_delay=1.5,
            log=log, label=f"{label}创建结界-返回" if label else "创建结界-返回",
            popup_handler=popup_handler,
        )
        if log:
            log.info(f"{tag}结界已创建，已返回寮界面")
        return True
    else:
        # 结界已存在，直接返回
        if log:
            log.info(f"{tag}结界已存在，无需创建")
        await click_template(
            adapter, capture_method, _TPL_BACK,
            timeout=5.0, settle=0.3, post_delay=1.5,
            log=log, label=f"{label}结界-返回" if label else "结界-返回",
            popup_handler=popup_handler,
        )
        return False
