"""
弹窗检测与关闭处理器

核心类 PopupHandler 负责：
1. 对一张截图扫描所有已注册弹窗
2. 找到匹配的弹窗后执行关闭动作
3. 验证关闭是否成功（支持连续多轮处理）
"""
from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Optional, Union

from loguru import logger

from ..vision.template import match_template
from ..vision.async_template import async_match_template
from ..vision.utils import ImageLike, load_image, to_gray
from .popups import DismissType, JihaoPopupException, PopupDef, PopupRegistry, popup_registry

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter
    from ..emu.async_adapter import AsyncEmulatorAdapter


class PopupHandler:
    """弹窗处理器：检测并关闭游戏中的意外弹窗"""

    def __init__(
        self,
        adapter: "Union[EmulatorAdapter, AsyncEmulatorAdapter]",
        capture_method: str = "adb",
        registry: PopupRegistry | None = None,
    ) -> None:
        self.adapter = adapter
        self.capture_method = capture_method
        self.registry = registry or popup_registry
        self._log = logger.bind(module="PopupHandler")

    # ── 异步适配辅助方法 ──

    async def _capture(self):
        """截图并直接返回 BGR ndarray。"""
        result = self.adapter.capture_ndarray(self.capture_method)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _adb_tap(self, addr: str, x: int, y: int) -> None:
        # AsyncEmulatorAdapter 没有直接的 adb.tap，统一用 adapter.tap
        from ..emu.async_adapter import AsyncEmulatorAdapter
        if isinstance(self.adapter, AsyncEmulatorAdapter):
            await self.adapter.tap(x, y)
        else:
            self.adapter.adb.tap(addr, x, y)

    async def _adb_shell(self, addr: str, cmd: str) -> None:
        from ..emu.async_adapter import AsyncEmulatorAdapter
        if isinstance(self.adapter, AsyncEmulatorAdapter):
            from ...core.thread_pool import run_in_io
            await run_in_io(self.adapter.adb.shell, addr, cmd)
        else:
            self.adapter.adb.shell(addr, cmd)

    def scan(self, image: ImageLike) -> Optional[PopupDef]:
        """扫描截图中是否存在已注册的弹窗（同步，CPU 密集）。

        按优先级顺序匹配，找到第一个即返回（短路）。

        Args:
            image: 截图数据（bytes / ndarray / path）

        Returns:
            匹配到的 PopupDef，未匹配返回 None
        """
        big = load_image(image)
        big_gray = to_gray(big)

        for popup in self.registry.all_sorted():
            tpl = popup.detect_template
            try:
                threshold = tpl.threshold or 0.85
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big_gray[y:y + h, x:x + w]
                    m = match_template(roi_img, tpl.path, threshold=threshold)
                else:
                    m = match_template(big_gray, tpl.path, threshold=threshold)
                if m:
                    self._log.info(
                        "检测到弹窗: {} (score={:.3f})",
                        popup.label, m.score,
                    )
                    return popup
            except Exception as e:
                self._log.debug("弹窗模板匹配异常 {}: {}", popup.id, e)
                continue
        return None

    async def async_scan(self, image: ImageLike) -> Optional[PopupDef]:
        """异步版 scan，将 CPU 密集的模板匹配 offload 到计算线程池。"""
        import functools
        from ...core.thread_pool import run_in_compute
        return await run_in_compute(functools.partial(self.scan, image))

    async def dismiss(self, popup: PopupDef) -> bool:
        """执行弹窗关闭动作序列。

        Args:
            popup: 要关闭的弹窗定义

        Returns:
            True 表示关闭动作已执行
        """
        addr = self.adapter.cfg.adb_addr

        for action in popup.dismiss_actions:
            if action.type == DismissType.TAP:
                await self._adb_tap(addr, action.tap_x, action.tap_y)

            elif action.type == DismissType.TAP_TEMPLATE:
                # 重新截图，模板匹配找到按钮后点击
                ss = await self._capture()
                tap_ok = False
                if ss is not None and action.template_path:
                    kwargs = {}
                    if action.template_threshold != 0.85:
                        kwargs["threshold"] = action.template_threshold
                    if action.template_roi:
                        big = load_image(ss)
                        rx, ry, rw, rh = action.template_roi
                        roi_img = big[ry:ry + rh, rx:rx + rw]
                        m = await async_match_template(roi_img, action.template_path, **kwargs)
                        if m:
                            # 坐标需要加回 ROI 偏移
                            cx, cy = m.random_point()
                            await self._adb_tap(addr, cx + rx, cy + ry)
                            tap_ok = True
                        else:
                            self._log.warning(
                                "弹窗 {} 关闭按钮模板未匹配 (ROI)",
                                popup.label,
                            )
                    else:
                        m = await async_match_template(ss, action.template_path, **kwargs)
                        if m:
                            await self._adb_tap(addr, *m.random_point())
                            tap_ok = True
                        else:
                            self._log.warning(
                                "弹窗 {} 关闭按钮模板未匹配",
                                popup.label,
                            )

                # 点击成功后等待模板消失
                if tap_ok and action.wait_disappear:
                    await self._wait_template_disappear(
                        action.template_path,
                        action.template_roi,
                        action.template_threshold,
                        timeout_ms=action.wait_disappear_timeout_ms,
                        poll_ms=action.wait_disappear_poll_ms,
                        label=popup.label,
                    )

            elif action.type == DismissType.TAP_SELF:
                # 重新截图匹配弹窗检测模板，点击其位置
                ss = await self._capture()
                if ss is not None:
                    tpl = popup.detect_template
                    threshold = tpl.threshold or 0.85
                    m = await async_match_template(ss, tpl.path, threshold=threshold)
                    if m:
                        await self._adb_tap(addr, *m.random_point())

            elif action.type == DismissType.BACK_KEY:
                await self._adb_shell(addr, "input keyevent KEYCODE_BACK")

            # 动作后等待
            if action.post_delay_ms > 0:
                await asyncio.sleep(action.post_delay_ms / 1000.0)

        self._log.info("弹窗 {} 关闭动作执行完毕", popup.label)
        return True

    async def _wait_template_disappear(
        self,
        template_path: str,
        roi: tuple | None = None,
        threshold: float = 0.85,
        *,
        timeout_ms: int = 5000,
        poll_ms: int = 500,
        label: str = "",
    ) -> bool:
        """轮询等待指定模板从画面中消失。"""
        elapsed = 0
        kwargs = {}
        if threshold != 0.85:
            kwargs["threshold"] = threshold

        while elapsed < timeout_ms:
            await asyncio.sleep(poll_ms / 1000.0)
            elapsed += poll_ms

            ss = await self._capture()
            if ss is None:
                continue

            if roi:
                big = load_image(ss)
                rx, ry, rw, rh = roi
                roi_img = big[ry:ry + rh, rx:rx + rw]
                m = await async_match_template(roi_img, template_path, **kwargs)
            else:
                m = await async_match_template(ss, template_path, **kwargs)

            if m is None:
                self._log.info("弹窗 {} 模板已消失 ({}ms)", label, elapsed)
                return True

        self._log.warning("弹窗 {} 等待模板消失超时 ({}ms)", label, timeout_ms)
        return False

    async def check_and_dismiss(
        self,
        image=None,
        *,
        max_rounds: int = 3,
    ) -> int:
        """检测并关闭弹窗（核心入口）。

        支持连续多轮处理（关闭一个弹窗后可能露出另一个弹窗）。

        Args:
            image: 截图（None 则自动截图），支持 bytes / ndarray
            max_rounds: 最大处理轮数（防止死循环）

        Returns:
            本次调用关闭的弹窗总数
        """
        dismissed = 0

        for round_idx in range(max_rounds):
            # 第一轮可复用传入的截图，后续轮次重新截图
            if image is None or round_idx > 0:
                image = await self._capture()
            if image is None:
                break

            popup = await self.async_scan(image)
            if popup is None:
                break

            # 祭号弹窗：不关闭，直接抛异常由上层处理
            if popup.id == "jihao":
                self._log.warning("检测到祭号弹窗，抛出异常")
                raise JihaoPopupException()

            self._log.info(
                "第 {} 轮弹窗处理: {} ({})",
                round_idx + 1, popup.label, popup.id,
            )

            success = await self.dismiss(popup)
            if success:
                dismissed += 1
            else:
                break

            # 清空 image 以便下一轮重新截图
            image = None

        if dismissed > 0:
            self._log.info("本次共关闭 {} 个弹窗", dismissed)
        return dismissed
