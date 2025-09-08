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

        # Preload big image once
        big = load_image(image)
        for ui in self.registry.all():
            s = self._score_ui(big, ui, thr)
            if s > best_score:
                best_score = s
                best_ui = ui.id

        if best_score >= thr:
            return UIDetectResult(ui=best_ui, score=best_score, debug={"threshold": thr})
        return UIDetectResult(ui="UNKNOWN", score=best_score, debug={"threshold": thr})

    def _score_ui(self, big_img, ui: UIDef, thr: float) -> float:
        score = 0.0
        # Evaluate templates
        for tpl in ui.templates:
            s = 0.0
            try:
                # If ROI defined, crop big image
                if tpl.roi:
                    x, y, w, h = tpl.roi
                    roi_img = big_img[y : y + h, x : x + w]
                    res = match_template(roi_img, tpl.path, threshold=tpl.threshold or thr)
                    s = res.score if res else 0.0
                else:
                    res = match_template(big_img, tpl.path, threshold=tpl.threshold or thr)
                    s = res.score if res else 0.0
            except Exception:
                s = 0.0
            score = max(score, s)
        # Validate pixels (if any)
        for px in ui.pixels:
            try:
                pm = pixel_match(big_img, px.x, px.y, px.rgb, tolerance=px.tolerance, color_space="rgb")
                if not pm["ok"]:
                    return 0.0
            except Exception:
                return 0.0
        return score


__all__ = ["UIDetector"]

