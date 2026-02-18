from __future__ import annotations

import functools
from typing import List, Optional, Sequence, Tuple

from ..vision import match_template, DEFAULT_THRESHOLD
from ..vision.utils import load_image, pixel_match, to_gray
from ..vision.template import _GRAY_TEMPLATE_CACHE
from .registry import TemplateDef, UIDef, UIRegistry
from .types import UIDetectResult


class UIDetector:
    def __init__(self, registry: UIRegistry, default_threshold: float = DEFAULT_THRESHOLD) -> None:
        self.registry = registry
        self.default_threshold = default_threshold

    def warmup(self) -> None:
        """预加载所有已注册模板到缓存，消除首次使用延迟。"""
        for ui in self.registry.all():
            for tpl in ui.templates:
                if tpl.path and isinstance(tpl.path, str):
                    try:
                        img = load_image(tpl.path)
                        gray = to_gray(img)
                        _GRAY_TEMPLATE_CACHE[tpl.path] = gray
                    except Exception:
                        pass

    # ── 公开检测 API ──

    def detect(
        self,
        image: bytes,
        *,
        threshold: Optional[float] = None,
        hints: Sequence[str] | None = None,
        anchors: bool = True,
    ) -> UIDetectResult:
        """两阶段 UI 检测。

        Phase 1（识别）：对每个 UI 只匹配 tag 模板，确定得分最高的 UI。
        Phase 2（锚点提取）：仅对赢家 UI 匹配其余锚点模板。

        Args:
            image: 截图数据（bytes / ndarray）
            threshold: 检测阈值
            hints: 优先检测的 UI id 列表（如上次 UI、目标 UI），排在扫描前面
            anchors: 是否执行 Phase 2 提取锚点（轮询场景传 False 跳过）
        """
        thr = threshold or self.default_threshold

        # 一次性加载和灰度化
        big = load_image(image)
        big_gray = to_gray(big)

        # ── Phase 1: Tag-only 快速识别 ──
        best_ui_id = "UNKNOWN"
        best_score = 0.0
        best_ui_def: UIDef | None = None

        ui_list = self._ordered_ui_list(hints)

        for ui in ui_list:
            s = self._match_tag_only(big_gray, ui, thr)

            # 像素校验（如有）
            if s >= thr and ui.pixels:
                if not self._check_pixels(big, ui):
                    s = 0.0

            if s > best_score:
                best_score = s
                best_ui_id = ui.id
                best_ui_def = ui
            if best_score >= 0.95:
                break

        if best_score < thr:
            return UIDetectResult(ui="UNKNOWN", score=best_score, debug={"threshold": thr})

        # ── Phase 2: 仅对赢家 UI 提取锚点 ──
        anchor_dict: dict = {}
        if anchors and best_ui_def is not None:
            anchor_dict = self._extract_anchors(big_gray, best_ui_def, thr)

        debug = {"anchors": anchor_dict, "threshold": thr}
        return UIDetectResult(ui=best_ui_id, score=best_score, debug=debug)

    async def async_detect(
        self,
        image: bytes,
        *,
        threshold: Optional[float] = None,
        hints: Sequence[str] | None = None,
        anchors: bool = True,
    ) -> UIDetectResult:
        """异步版本的 detect，将整个检测 offload 到计算线程池。"""
        from ...core.thread_pool import run_in_compute
        return await run_in_compute(
            functools.partial(
                self.detect, image,
                threshold=threshold, hints=hints, anchors=anchors,
            )
        )

    # ── 内部方法 ──

    def _ordered_ui_list(self, hints: Sequence[str] | None) -> List[UIDef]:
        """根据 hints 调整 UI 扫描顺序：hints 中的 UI 优先检测。"""
        all_uis = self.registry.all()
        if not hints:
            return all_uis

        priority: list[UIDef] = []
        rest: list[UIDef] = []
        hint_set = set(hints)
        for ui in all_uis:
            if ui.id in hint_set:
                priority.append(ui)
            else:
                rest.append(ui)
        # 保持 hints 中的相对顺序
        priority.sort(key=lambda u: list(hints).index(u.id) if u.id in hints else 999)
        return priority + rest

    def _match_tag_only(self, big_gray, ui: UIDef, thr: float) -> float:
        """Phase 1: 只匹配 tag 模板返回分数。无 tag 的 UI 匹配所有模板取最大值。"""
        if ui._tag_template is not None:
            return self._match_one_template(big_gray, ui._tag_template, thr)

        # 无 tag（如 SHIXIAO）：匹配所有模板取最大值
        score = 0.0
        for tpl in ui.templates:
            s = self._match_one_template(big_gray, tpl, thr)
            score = max(score, s)
        return score

    def _match_one_template(self, big_gray, tpl: TemplateDef, thr: float) -> float:
        """匹配单个模板，返回分数。"""
        try:
            if tpl.roi:
                x, y, w, h = tpl.roi
                roi_img = big_gray[y : y + h, x : x + w]
                res = match_template(roi_img, tpl.path, threshold=tpl.threshold or thr)
            else:
                res = match_template(big_gray, tpl.path, threshold=tpl.threshold or thr)
            return res.score if res else 0.0
        except Exception:
            return 0.0

    def _extract_anchors(self, big_gray, ui: UIDef, thr: float) -> dict[str, dict]:
        """Phase 2: 对赢家 UI 匹配所有模板（含 tag），提取锚点坐标。"""
        anchors: dict[str, dict] = {}
        for tpl in ui.templates:
            try:
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big_gray[y : y + h, x : x + w]
                    res = match_template(roi_img, tpl.path, threshold=tpl.threshold or thr)
                    if res:
                        cx, cy = res.center
                        anchors[tpl.name] = {
                            "x": int(cx + x),
                            "y": int(cy + y),
                            "score": float(res.score),
                        }
                else:
                    res = match_template(big_gray, tpl.path, threshold=tpl.threshold or thr)
                    if res:
                        cx, cy = res.center
                        anchors[tpl.name] = {
                            "x": int(cx),
                            "y": int(cy),
                            "score": float(res.score),
                        }
            except Exception:
                pass
        return anchors

    def _check_pixels(self, big_img, ui: UIDef) -> bool:
        """校验像素约束。全部通过返回 True。"""
        for px in ui.pixels:
            try:
                pm = pixel_match(big_img, px.x, px.y, px.rgb, tolerance=px.tolerance, color_space="rgb")
                if not pm["ok"]:
                    return False
            except Exception:
                return False
        return True


__all__ = ["UIDetector"]
