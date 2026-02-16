"""
御魂关卡等级检测 - 基于 HSV 颜色分析

检测御魂界面左侧竖排矩形框的状态：
- 淡黄色 = 当前选中的关卡
- 较浅色（灰白）= 已解锁未选中
- 灰色（较深）= 未解锁/锁定
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .utils import ImageLike, load_image


class LevelState(str, Enum):
    SELECTED = "selected"    # 淡黄色 - 当前选中
    UNLOCKED = "unlocked"    # 较浅色 - 已解锁未选中
    LOCKED = "locked"        # 灰色 - 未解锁


@dataclass
class YuHunLevel:
    index: int                                 # 层级编号（1-indexed，从上到下）
    state: LevelState                          # 状态
    center: Tuple[int, int]                    # 格子中心坐标 (x, y)
    roi: Tuple[int, int, int, int]             # (x, y, w, h) 检测区域
    avg_hsv: Tuple[float, float, float]        # 平均 HSV 值（调试用）


# ── 关卡框布局常量（960×540 分辨率）──
# 左侧关卡框采样区域的 x 范围（取填充区域避免左侧装饰边框干扰）
_ROI_X_START = 100
_ROI_X_END = 200

# 各层级 y 范围（取框内核心填充区域，避开顶部/底部装饰边框）
_LEVEL_Y_RANGES: List[Tuple[int, int]] = [
    (110, 160),     # 第1层
    (195, 245),     # 第2层
    (277, 327),     # 第3层
    (358, 408),     # 第4层
]

# ── HSV 阈值（基于实际截图校准）──
# 选中（金色填充）：H ≈ 15-25, S > 40, V > 160
_SELECTED_H_MIN = 10
_SELECTED_H_MAX = 28
_SELECTED_S_MIN = 40
_SELECTED_V_MIN = 160

# 已解锁 vs 锁定 的 V 值分界线
# 已解锁（蓝灰色较亮）：H > 80, V > 162
# 锁定（蓝灰色较暗）：H > 80, V <= 162
_UNLOCKED_V_MIN = 162


def detect_yuhun_levels(
    image: ImageLike,
    start_index: int = 1,
) -> List[YuHunLevel]:
    """检测御魂界面中当前可见的关卡层级状态。

    Args:
        image: 截图（960×540 BGR 图像）
        start_index: 当前视口中第一个格子对应的实际层级编号（1-indexed）。
                     默认 1（未滚动时），滚动后由调用方传入。

    Returns:
        层级列表，从上到下排列（index 从 start_index 起始）
    """
    img = load_image(image)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    levels: List[YuHunLevel] = []
    for slot_idx, (y_start, y_end) in enumerate(_LEVEL_Y_RANGES):
        actual_index = start_index + slot_idx
        if actual_index > 10:
            break

        roi = hsv[y_start:y_end, _ROI_X_START:_ROI_X_END]
        avg_h = float(np.mean(roi[:, :, 0]))
        avg_s = float(np.mean(roi[:, :, 1]))
        avg_v = float(np.mean(roi[:, :, 2]))

        # 判定状态
        if (_SELECTED_H_MIN <= avg_h <= _SELECTED_H_MAX
                and avg_s >= _SELECTED_S_MIN
                and avg_v >= _SELECTED_V_MIN):
            state = LevelState.SELECTED
        elif avg_v >= _UNLOCKED_V_MIN:
            state = LevelState.UNLOCKED
        else:
            state = LevelState.LOCKED

        center_x = (_ROI_X_START + _ROI_X_END) // 2
        center_y = (y_start + y_end) // 2
        levels.append(YuHunLevel(
            index=actual_index,
            state=state,
            center=(center_x, center_y),
            roi=(_ROI_X_START, y_start,
                 _ROI_X_END - _ROI_X_START, y_end - y_start),
            avg_hsv=(round(avg_h, 1), round(avg_s, 1), round(avg_v, 1)),
        ))

    return levels


def find_highest_unlocked_level(image: ImageLike) -> Optional[YuHunLevel]:
    """找到最高已解锁层级（最底部的非锁定层 = 最高难度）。

    优先返回最后一个 UNLOCKED/SELECTED 状态的层级。
    全部锁定时返回 None。
    """
    levels = detect_yuhun_levels(image)
    available = [lv for lv in levels if lv.state != LevelState.LOCKED]
    if not available:
        return None
    # 返回 index 最大的（最底部 = 最高难度解锁层）
    return available[-1]


__all__ = [
    "LevelState",
    "YuHunLevel",
    "detect_yuhun_levels",
    "find_highest_unlocked_level",
]
