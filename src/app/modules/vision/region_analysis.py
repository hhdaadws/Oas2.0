"""
区域亮度分析工具

提供 ROI 区域的亮度统计功能，用于对话框检测等场景。
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .utils import ImageLike, load_image, to_gray


def region_mean_brightness(
    image: ImageLike,
    roi: Tuple[int, int, int, int],
) -> float:
    """计算指定 ROI 区域的平均灰度亮度。

    Args:
        image: 图片（path/bytes/np.ndarray）
        roi: (x, y, w, h) 区域

    Returns:
        平均亮度值 [0, 255]
    """
    img = to_gray(load_image(image))
    x, y, w, h = roi
    region = img[y : y + h, x : x + w]
    return float(np.mean(region))


__all__ = ["region_mean_brightness"]
