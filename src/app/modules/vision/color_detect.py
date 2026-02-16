"""
Color-based detection utilities.

Provides red dot (notification badge) detection using HSV color space
filtering, morphological denoising, and contour circularity analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2  # type: ignore
import numpy as np

from .utils import ImageLike, load_image


@dataclass
class RedDotResult:
    """红点检测结果"""
    found: bool
    x: int = 0
    y: int = 0
    radius: int = 0
    area: int = 0
    confidence: float = 0.0

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x, self.y)


_NOT_FOUND = RedDotResult(found=False)


def detect_red_dot(
    image: ImageLike,
    *,
    roi: Optional[Tuple[int, int, int, int]] = None,
    min_area: int = 20,
    max_area: int = 600,
    min_circularity: float = 0.45,
    h_ranges: Tuple[Tuple[int, int], Tuple[int, int]] = ((0, 10), (170, 180)),
    s_range: Tuple[int, int] = (80, 255),
    v_range: Tuple[int, int] = (120, 255),
) -> RedDotResult:
    """在图像中检测红色圆点通知标记。

    算法:
      1. 加载图像，按 ROI 裁切
      2. BGR → HSV
      3. 双段 H 范围 mask 合并（红色跨越 H=0/180 边界）
      4. 椭圆核开运算去噪
      5. 轮廓分析，按面积 + 圆度过滤
      6. 取圆度最高的候选，minEnclosingCircle 计算中心和半径

    Args:
        image: 截图 (path / bytes / np.ndarray)，BGR 格式
        roi: 检测区域 (x, y, w, h)，None 则全图
        min_area: 红点最小像素面积
        max_area: 红点最大像素面积
        min_circularity: 轮廓圆度下限 (0~1)
        h_ranges: HSV H 通道两段红色范围
        s_range: HSV S 通道范围
        v_range: HSV V 通道范围

    Returns:
        RedDotResult，found=True 时坐标为原图坐标系
    """
    img = load_image(image)
    offset_x, offset_y = 0, 0
    if roi is not None:
        rx, ry, rw, rh = roi
        img = img[ry:ry + rh, rx:rx + rw]
        offset_x, offset_y = rx, ry

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    (h_lo1, h_hi1), (h_lo2, h_hi2) = h_ranges
    s_lo, s_hi = s_range
    v_lo, v_hi = v_range

    mask1 = cv2.inRange(hsv, np.array([h_lo1, s_lo, v_lo]), np.array([h_hi1, s_hi, v_hi]))
    mask2 = cv2.inRange(hsv, np.array([h_lo2, s_lo, v_lo]), np.array([h_hi2, s_hi, v_hi]))
    mask = cv2.bitwise_or(mask1, mask2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _NOT_FOUND

    best_cnt = None
    best_circ = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circ = (4.0 * np.pi * area) / (perimeter * perimeter)
        if circ < min_circularity:
            continue
        if circ > best_circ:
            best_circ = circ
            best_cnt = cnt

    if best_cnt is None:
        return _NOT_FOUND

    (cx, cy), radius = cv2.minEnclosingCircle(best_cnt)
    return RedDotResult(
        found=True,
        x=int(cx) + offset_x,
        y=int(cy) + offset_y,
        radius=max(1, int(radius)),
        area=int(cv2.contourArea(best_cnt)),
        confidence=round(best_circ, 3),
    )


def has_red_dot_on_match(
    image: ImageLike,
    match: "Match",
    *,
    corner: str = "top_right",
    margin: int = 4,
    **kwargs,
) -> RedDotResult:
    """检测模板匹配结果的指定角落是否有红点。

    根据 match 区域自动计算 ROI（取指定角落 1/2 区域 + margin 外扩）。

    Args:
        image: 完整截图
        match: Match 对象（来自 template.match_template）
        corner: "top_right" / "top_left" / "bottom_right" / "bottom_left"
        margin: ROI 向外扩展像素数
        **kwargs: 传递给 detect_red_dot 的参数
    """
    half_w = match.w // 2
    half_h = match.h // 2

    if corner == "top_right":
        rx = match.x + half_w - margin
        ry = match.y - margin
    elif corner == "top_left":
        rx = match.x - margin
        ry = match.y - margin
    elif corner == "bottom_right":
        rx = match.x + half_w - margin
        ry = match.y + half_h - margin
    else:
        rx = match.x - margin
        ry = match.y + half_h - margin

    img = load_image(image)
    img_h, img_w = img.shape[:2]
    rx = max(0, rx)
    ry = max(0, ry)
    rw = min(half_w + 2 * margin, img_w - rx)
    rh = min(half_h + 2 * margin, img_h - ry)

    return detect_red_dot(image, roi=(rx, ry, rw, rh), **kwargs)


def detect_red_markers(
    image: ImageLike,
    *,
    roi: Optional[Tuple[int, int, int, int]] = None,
    min_area: int = 8,
    max_area: int = 300,
    h_ranges: Tuple[Tuple[int, int], Tuple[int, int]] = ((0, 10), (170, 180)),
    s_range: Tuple[int, int] = (80, 255),
    v_range: Tuple[int, int] = (120, 255),
) -> List[Tuple[int, int]]:
    """检测 ROI 内所有红色标记的中心坐标（原图坐标系）。

    用于成就界面左侧分类的红色菱形检测。
    不做圆度过滤，仅按颜色和面积筛选。
    返回按 y 坐标升序排列的中心点列表。
    """
    img = load_image(image)
    offset_x, offset_y = 0, 0
    if roi is not None:
        rx, ry, rw, rh = roi
        img = img[ry:ry + rh, rx:rx + rw]
        offset_x, offset_y = rx, ry

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    (h_lo1, h_hi1), (h_lo2, h_hi2) = h_ranges
    s_lo, s_hi = s_range
    v_lo, v_hi = v_range

    mask1 = cv2.inRange(hsv, np.array([h_lo1, s_lo, v_lo]), np.array([h_hi1, s_hi, v_hi]))
    mask2 = cv2.inRange(hsv, np.array([h_lo2, s_lo, v_lo]), np.array([h_hi2, s_hi, v_hi]))
    mask = cv2.bitwise_or(mask1, mask2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    results: List[Tuple[int, int]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        m = cv2.moments(cnt)
        if m["m00"] == 0:
            continue
        cx = int(m["m10"] / m["m00"]) + offset_x
        cy = int(m["m01"] / m["m00"]) + offset_y
        results.append((cx, cy))

    results.sort(key=lambda p: p[1])
    return results


@dataclass
class LockState:
    """结界突破阵容锁定检测结果"""
    locked: bool
    score: float = 0.0
    center: Tuple[int, int] = (0, 0)


# 锁定状态模板
_TPL_LOCK_JIEKAI = "assets/ui/templates/lock_jiekai.png"
# 锁图标所在 ROI (x, y, w, h)，限制搜索范围提高准确率
_LOCK_ROI = (570, 400, 100, 80)
# 匹配阈值：lock=1.0, unlock=0.77，0.85 可以完美区分
_LOCK_THRESHOLD = 0.85


def detect_jiekai_lock(
    image: ImageLike,
    *,
    threshold: float = _LOCK_THRESHOLD,
    roi: Optional[Tuple[int, int, int, int]] = _LOCK_ROI,
) -> LockState:
    """检测界面的阵容是否已锁定。

    通过模板匹配锁定状态的金色锁图标来判断。
    锁定状态匹配得分 ~1.0，未锁定状态得分 ~0.77。

    Args:
        image: 截图 (path / bytes / np.ndarray)，960×540 分辨率
        threshold: 匹配阈值，默认 0.85
        roi: 搜索区域 (x, y, w, h)，默认 _LOCK_ROI（结界突破界面）。
             传 None 则在全图搜索（探索等场景锁位置不同时使用）。

    Returns:
        LockState，locked=True 表示阵容已锁定
    """
    from .template import match_template

    img = load_image(image)

    if roi is not None:
        rx, ry, rw, rh = roi
        search_img = img[ry:ry + rh, rx:rx + rw]
        offset_x, offset_y = rx, ry
    else:
        search_img = img
        offset_x, offset_y = 0, 0

    m = match_template(search_img, _TPL_LOCK_JIEKAI, threshold=threshold)
    if m is not None:
        center = (m.center[0] + offset_x, m.center[1] + offset_y)
        return LockState(locked=True, score=m.score, center=center)

    # 未匹配 - 获取实际得分用于调试
    m_any = match_template(search_img, _TPL_LOCK_JIEKAI, threshold=0.0)
    score = m_any.score if m_any else 0.0
    return LockState(locked=False, score=score)


# 探索界面专用锁模板和 ROI
_TPL_LOCK_ZHENRONG = "assets/ui/templates/zhenrong_lock.png"
# "固定阵容"按钮区域 (x, y, w, h)
# lock=0.95, unlock=0.35 in ROI → threshold=0.80 可靠区分
_ZHENRONG_LOCK_ROI = (650, 480, 110, 60)
_ZHENRONG_LOCK_THRESHOLD = 0.80


def detect_explore_lock(
    image: ImageLike,
    *,
    threshold: float = _ZHENRONG_LOCK_THRESHOLD,
    roi: Optional[Tuple[int, int, int, int]] = _ZHENRONG_LOCK_ROI,
) -> LockState:
    """检测探索界面的阵容锁定状态。

    使用探索专用的 zhenrong_lock.png 模板和 ROI。
    锁定得分 ~0.95，未锁定得分 ~0.35。

    Args:
        image: 截图 (path / bytes / np.ndarray)，960×540 分辨率
        threshold: 匹配阈值，默认 0.80
        roi: 搜索区域 (x, y, w, h)，默认 _ZHENRONG_LOCK_ROI

    Returns:
        LockState，locked=True 表示阵容已锁定
    """
    from .template import match_template

    img = load_image(image)

    if roi is not None:
        rx, ry, rw, rh = roi
        search_img = img[ry:ry + rh, rx:rx + rw]
        offset_x, offset_y = rx, ry
    else:
        search_img = img
        offset_x, offset_y = 0, 0

    m = match_template(search_img, _TPL_LOCK_ZHENRONG, threshold=threshold)
    if m is not None:
        center = (m.center[0] + offset_x, m.center[1] + offset_y)
        return LockState(locked=True, score=m.score, center=center)

    # 未匹配 - 获取实际得分用于调试
    m_any = match_template(search_img, _TPL_LOCK_ZHENRONG, threshold=0.0)
    score = m_any.score if m_any else 0.0
    return LockState(locked=False, score=score)


def count_purple_gouyu(
    image: ImageLike,
    *,
    roi: Optional[Tuple[int, int, int, int]] = None,
    min_area: int = 8,
    max_area: int = 200,
    h_range: Tuple[int, int] = (120, 160),
    s_range: Tuple[int, int] = (40, 255),
    v_range: Tuple[int, int] = (80, 255),
) -> int:
    """计算 ROI 内紫色勾玉的数量，用于判定式神星级。

    算法与 detect_red_markers 一致，仅颜色范围改为紫色。

    Args:
        image: 截图 (path / bytes / np.ndarray)，BGR 格式
        roi: 检测区域 (x, y, w, h)，None 则全图
        min_area: 勾玉最小像素面积
        max_area: 勾玉最大像素面积
        h_range: HSV H 通道紫色范围（OpenCV 0-180）
        s_range: HSV S 通道范围
        v_range: HSV V 通道范围

    Returns:
        检测到的紫色勾玉数量（即星级）
    """
    img = load_image(image)
    if roi is not None:
        rx, ry, rw, rh = roi
        img = img[ry:ry + rh, rx:rx + rw]

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    h_lo, h_hi = h_range
    s_lo, s_hi = s_range
    v_lo, v_hi = v_range

    mask = cv2.inRange(
        hsv,
        np.array([h_lo, s_lo, v_lo]),
        np.array([h_hi, s_hi, v_hi]),
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0

    count = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            count += 1

    return count


__all__ = [
    "RedDotResult",
    "detect_red_dot",
    "has_red_dot_on_match",
    "detect_red_markers",
    "LockState",
    "detect_jiekai_lock",
    "count_purple_gouyu",
    "detect_explore_lock",
]
