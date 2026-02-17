from __future__ import annotations

import functools
from typing import Optional, Tuple

from ..vision import match_template, DEFAULT_THRESHOLD
from ..vision.utils import load_image, pixel_match, to_gray
from ..vision.template import _GRAY_TEMPLATE_CACHE
from .registry import UIDef, UIRegistry
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

    def detect(self, image: bytes, *, threshold: Optional[float] = None) -> UIDetectResult:
        """Detect UI by scanning registered UIDef entries.

        Strategy: for each UI, compute max template score; apply pixel anchors if present.
        Return best UI above threshold; otherwise ui="UNKNOWN".
        """
        thr = threshold or self.default_threshold
        best_ui = "UNKNOWN"
        best_score = 0.0
        best_debug: dict = {"anchors": {}}

        # Preload big image once and convert to grayscale for reuse
        big = load_image(image)
        big_gray = to_gray(big)
        for ui in self.registry.all():
            s, debug = self._score_ui(big, big_gray, ui, thr)
            if s > best_score:
                best_score = s
                best_ui = ui.id
                best_debug = debug
            if best_score >= 0.95:
                break

        if best_score >= thr:
            best_debug["threshold"] = thr
            return UIDetectResult(ui=best_ui, score=best_score, debug=best_debug)
        return UIDetectResult(ui="UNKNOWN", score=best_score, debug={"threshold": thr})

    def _score_ui(self, big_img, big_gray, ui: UIDef, thr: float) -> tuple[float, dict]:
        score = 0.0
        tag_score = 0.0
        anchors: dict[str, dict] = {}
        has_tag = bool(ui.tag)
        # Evaluate templates
        for tpl in ui.templates:
            s = 0.0
            try:
                # If ROI defined, crop big image (use grayscale for matching)
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big_gray[y : y + h, x : x + w]
                    res = match_template(roi_img, tpl.path, threshold=tpl.threshold or thr)
                    if res:
                        s = res.score
                        cx, cy = res.center
                        anchors[tpl.name] = {
                            "x": int(cx + x),
                            "y": int(cy + y),
                            "score": float(s),
                        }
                    else:
                        s = 0.0
                else:
                    res = match_template(big_gray, tpl.path, threshold=tpl.threshold or thr)
                    if res:
                        s = res.score
                        cx, cy = res.center
                        anchors[tpl.name] = {
                            "x": int(cx),
                            "y": int(cy),
                            "score": float(s),
                        }
                    else:
                        s = 0.0
            except Exception:
                s = 0.0
            score = max(score, s)
            # 如果该模板是 tag 模板，记录其分数
            if has_tag and tpl.name == ui.tag:
                tag_score = s
        # Validate pixels (if any)
        for px in ui.pixels:
            try:
                pm = pixel_match(big_img, px.x, px.y, px.rgb, tolerance=px.tolerance, color_space="rgb")
                if not pm["ok"]:
                    return 0.0, {"anchors": {}}
            except Exception:
                return 0.0, {"anchors": {}}
        # 如果设置了 tag，使用 tag 模板的分数作为界面识别分数
        final_score = tag_score if has_tag else score
        return final_score, {"anchors": anchors}

    async def async_detect(self, image: bytes, *, threshold: Optional[float] = None) -> UIDetectResult:
        """异步版本的 detect，将整个检测 offload 到计算线程池。"""
        from ...core.thread_pool import run_in_compute
        return await run_in_compute(
            functools.partial(self.detect, image, threshold=threshold)
        )


__all__ = ["UIDetector"]

