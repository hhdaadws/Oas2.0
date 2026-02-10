"""
弹窗检测与关闭处理器

核心类 PopupHandler 负责：
1. 对一张截图扫描所有已注册弹窗
2. 找到匹配的弹窗后执行关闭动作
3. 验证关闭是否成功（支持连续多轮处理）
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from loguru import logger

from ..vision.template import match_template
from ..vision.utils import load_image
from .popups import DismissType, PopupDef, PopupRegistry, popup_registry

if TYPE_CHECKING:
    from ..emu.adapter import EmulatorAdapter


class PopupHandler:
    """弹窗处理器：检测并关闭游戏中的意外弹窗"""

    def __init__(
        self,
        adapter: EmulatorAdapter,
        capture_method: str = "adb",
        registry: PopupRegistry | None = None,
    ) -> None:
        self.adapter = adapter
        self.capture_method = capture_method
        self.registry = registry or popup_registry
        self._log = logger.bind(module="PopupHandler")

    def scan(self, image: bytes) -> Optional[PopupDef]:
        """扫描截图中是否存在已注册的弹窗。

        按优先级顺序匹配，找到第一个即返回（短路）。

        Args:
            image: 截图的 bytes 数据

        Returns:
            匹配到的 PopupDef，未匹配返回 None
        """
        big = load_image(image)

        for popup in self.registry.all_sorted():
            tpl = popup.detect_template
            try:
                threshold = tpl.threshold or 0.85
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big[y:y + h, x:x + w]
                    m = match_template(roi_img, tpl.path, threshold=threshold)
                else:
                    m = match_template(big, tpl.path, threshold=threshold)
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
                self.adapter.adb.tap(addr, action.tap_x, action.tap_y)

            elif action.type == DismissType.TAP_TEMPLATE:
                # 重新截图，模板匹配找到按钮后点击
                ss = self.adapter.capture(self.capture_method)
                if ss and action.template_path:
                    kwargs = {}
                    if action.template_threshold != 0.85:
                        kwargs["threshold"] = action.template_threshold
                    if action.template_roi:
                        big = load_image(ss)
                        rx, ry, rw, rh = action.template_roi
                        roi_img = big[ry:ry + rh, rx:rx + rw]
                        m = match_template(roi_img, action.template_path, **kwargs)
                        if m:
                            # 坐标需要加回 ROI 偏移
                            cx, cy = m.center
                            self.adapter.adb.tap(addr, cx + rx, cy + ry)
                        else:
                            self._log.warning(
                                "弹窗 {} 关闭按钮模板未匹配 (ROI)",
                                popup.label,
                            )
                    else:
                        m = match_template(ss, action.template_path, **kwargs)
                        if m:
                            self.adapter.adb.tap(addr, *m.center)
                        else:
                            self._log.warning(
                                "弹窗 {} 关闭按钮模板未匹配",
                                popup.label,
                            )

            elif action.type == DismissType.TAP_SELF:
                # 重新截图匹配弹窗检测模板，点击其位置
                ss = self.adapter.capture(self.capture_method)
                if ss:
                    tpl = popup.detect_template
                    threshold = tpl.threshold or 0.85
                    m = match_template(ss, tpl.path, threshold=threshold)
                    if m:
                        self.adapter.adb.tap(addr, *m.center)

            elif action.type == DismissType.BACK_KEY:
                self.adapter.adb.shell(addr, "input keyevent KEYCODE_BACK")

            # 动作后等待
            if action.post_delay_ms > 0:
                await asyncio.sleep(action.post_delay_ms / 1000.0)

        self._log.info("弹窗 {} 关闭动作执行完毕", popup.label)
        return True

    async def check_and_dismiss(
        self,
        image: bytes | None = None,
        *,
        max_rounds: int = 3,
    ) -> int:
        """检测并关闭弹窗（核心入口）。

        支持连续多轮处理（关闭一个弹窗后可能露出另一个弹窗）。

        Args:
            image: 截图（None 则自动截图）
            max_rounds: 最大处理轮数（防止死循环）

        Returns:
            本次调用关闭的弹窗总数
        """
        dismissed = 0

        for round_idx in range(max_rounds):
            # 第一轮可复用传入的截图，后续轮次重新截图
            if image is None or round_idx > 0:
                image = self.adapter.capture(self.capture_method)
            if image is None:
                break

            popup = self.scan(image)
            if popup is None:
                break

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
