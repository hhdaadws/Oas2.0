from __future__ import annotations

from typing import Optional, Tuple

from ..vision import match_template, DEFAULT_THRESHOLD
from ..vision.utils import load_image, pixel_match
from .registry import UIDef, UIRegistry
from .types import UIDetectResult


class UIDetector:
    def __init__(self, registry: UIRegistry, default_threshold: float = DEFAULT_THRESHOLD) -> None:
        self.registry = registry
        self.default_threshold = default_threshold

    def detect(self, image: bytes, *, threshold: Optional[float] = None) -> UIDetectResult:
        """Detect UI by scanning registered UIDef entries.

        Strategy: for each UI, compute max template score; apply pixel anchors if present.
        Return best UI above threshold; otherwise ui="UNKNOWN".
        """
        thr = threshold or self.default_threshold
        best_ui = "UNKNOWN"
        best_score = 0.0
        best_debug: dict = {"anchors": {}}

        # Preload big image once
        big = load_image(image)
        for ui in self.registry.all():
            s, debug = self._score_ui(big, ui, thr)
            if s > best_score:
                best_score = s
                best_ui = ui.id
                best_debug = debug

        if best_score >= thr:
            best_debug["threshold"] = thr
            return UIDetectResult(ui=best_ui, score=best_score, debug=best_debug)
        return UIDetectResult(ui="UNKNOWN", score=best_score, debug={"threshold": thr})

    def _score_ui(self, big_img, ui: UIDef, thr: float) -> tuple[float, dict]:
        score = 0.0
        tag_score = 0.0
        anchors: dict[str, dict] = {}
        has_tag = bool(ui.tag)
        # Evaluate templates
        for tpl in ui.templates:
            s = 0.0
            try:
                # If ROI defined, crop big image
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big_img[y : y + h, x : x + w]
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
                    res = match_template(big_img, tpl.path, threshold=tpl.threshold or thr)
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


__all__ = ["UIDetector"]

