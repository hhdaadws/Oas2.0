"""
Template matching utilities.

Features:
- Single best match with default threshold 0.85
- Find all matches above threshold
- Return relative coordinates within the large image (top-left origin),
  including the clickable center of the matched template
"""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple
import cv2  # type: ignore
import numpy as np

from .utils import ImageLike, load_image, to_gray


DEFAULT_THRESHOLD = 0.85
_GRAY_TEMPLATE_CACHE: dict[str, np.ndarray] = {}
_CACHE_LOCK = threading.Lock()


@dataclass
class Match:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def random_point(self, margin: float = 0.2) -> Tuple[int, int]:
        """在模板匹配区域内生成随机点击坐标（每边向内缩 margin 比例）。"""
        margin = max(0.0, min(margin, 0.45))
        mx = int(self.w * margin)
        my = int(self.h * margin)
        rx = random.randint(self.x + mx, self.x + self.w - 1 - mx)
        ry = random.randint(self.y + my, self.y + self.h - 1 - my)
        return (rx, ry)


def _ensure_sizes(big: np.ndarray, small: np.ndarray) -> None:
    hb, wb = big.shape[:2]
    hs, ws = small.shape[:2]
    if hs > hb or ws > wb:
        raise ValueError(f"Template larger than image: template {ws}x{hs}, image {wb}x{hb}")


def match_template(
    image: ImageLike,
    template: ImageLike,
    *,
    threshold: Optional[float] = None,
    method: int = cv2.TM_CCOEFF_NORMED,
) -> Optional[Match]:
    """Find the best match location for template in image.

    Args:
        image: large image (path/bytes/np.ndarray)
        template: small image (path/bytes/np.ndarray)
        threshold: match threshold (default 0.85 if None)
        method: OpenCV matchTemplate method (default TM_CCOEFF_NORMED)

    Returns:
        Match or None if best score is below threshold.
    """
    thr = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    loaded = load_image(image)
    img = loaded if loaded.ndim == 2 else to_gray(loaded)
    if isinstance(template, str):
        tpl = _GRAY_TEMPLATE_CACHE.get(template)
        if tpl is None:
            with _CACHE_LOCK:
                tpl = _GRAY_TEMPLATE_CACHE.get(template)
                if tpl is None:
                    tpl = to_gray(load_image(template))
                    _GRAY_TEMPLATE_CACHE[template] = tpl
    else:
        tpl_loaded = load_image(template)
        tpl = tpl_loaded if tpl_loaded.ndim == 2 else to_gray(tpl_loaded)
    _ensure_sizes(img, tpl)

    res = cv2.matchTemplate(img, tpl, method)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
        # lower is better
        score = 1.0 - float(min_val)
        x, y = min_loc
    else:
        score = float(max_val)
        x, y = max_loc

    h, w = tpl.shape[:2]
    if score < thr:
        return None
    return Match(x=x, y=y, w=w, h=h, score=score)


def find_all_templates(
    image: ImageLike,
    template: ImageLike,
    *,
    threshold: Optional[float] = None,
    method: int = cv2.TM_CCOEFF_NORMED,
) -> List[Match]:
    """Find all matches above threshold.

    Returns matches sorted by score (desc).
    """
    thr = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    loaded = load_image(image)
    img = loaded if loaded.ndim == 2 else to_gray(loaded)
    if isinstance(template, str):
        tpl = _GRAY_TEMPLATE_CACHE.get(template)
        if tpl is None:
            with _CACHE_LOCK:
                tpl = _GRAY_TEMPLATE_CACHE.get(template)
                if tpl is None:
                    tpl = to_gray(load_image(template))
                    _GRAY_TEMPLATE_CACHE[template] = tpl
    else:
        tpl_loaded = load_image(template)
        tpl = tpl_loaded if tpl_loaded.ndim == 2 else to_gray(tpl_loaded)
    _ensure_sizes(img, tpl)

    res = cv2.matchTemplate(img, tpl, method)
    h, w = tpl.shape[:2]

    matches: List[Match] = []
    if method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
        # For SQDIFF, good matches have low values. Convert to score=1-val
        mask = np.where(res <= (1.0 - thr))
        for y, x in zip(mask[0].tolist(), mask[1].tolist()):
            val = float(res[y, x])
            score = 1.0 - val
            if score >= thr:
                matches.append(Match(x=x, y=y, w=w, h=h, score=score))
    else:
        loc = np.where(res >= thr)
        for y, x in zip(loc[0].tolist(), loc[1].tolist()):
            val = float(res[y, x])
            matches.append(Match(x=x, y=y, w=w, h=h, score=val))

    # Sort by score descending
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


__all__ = [
    "DEFAULT_THRESHOLD",
    "Match",
    "match_template",
    "find_all_templates",
]

