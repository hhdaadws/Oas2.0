"""
战斗准备预设面板格子检测。

在战斗准备界面点击"预设"后，面板显示：
- 左侧窄列：分组格子（分组1、分组2、…）
- 右侧主区域：选中分组内的阵容格子（阵容1、阵容2、…）

采用行均值亮度分割算法（与 grid_detect.detect_right_column_cells 相同原理），
增强了对首个格子的检测：面板顶部没有暗色分隔线时，将扫描起点视为隐式边界。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .utils import ImageLike, load_image, to_gray

# ── 分组格子 ROI（左侧窄列，960×540 分辨率）──
# 分组区域 x≈24-122，暗色分隔线在 y≈168-177, y≈223-224, y≈270+
_GROUP_X_START = 30
_GROUP_X_END = 110
_GROUP_Y_START = 168
_GROUP_Y_END = 270
_GROUP_DARK_THRESHOLD = 80
_GROUP_MIN_CELL_HEIGHT = 25

# ── 阵容格子 ROI（右侧主区域，960×540 分辨率）──
# 阵容区域 x≈130-350，顶部 y≈24-168 为空白/标题区域（非阵容格子）
# 实际阵容格子从 y≈174 开始，暗色分隔线在 y≈169-173, y≈263-264, y≈351+
_LINEUP_X_START = 140
_LINEUP_X_END = 330
_LINEUP_Y_START = 168
_LINEUP_Y_END = 440
_LINEUP_DARK_THRESHOLD = 80
_LINEUP_MIN_CELL_HEIGHT = 30

# 分组格子点击时使用的 x 坐标中心
_GROUP_TAP_X_CENTER = 73
# 阵容格子点击时使用的 x 坐标中心（面板主区域中心而非检测条带中心）
_LINEUP_TAP_X_CENTER = 240


@dataclass
class BattleCellInfo:
    """预设面板格子信息"""
    index: int                    # 编号 (1-indexed, 从上到下)
    top: int                      # 格子顶部 y
    bottom: int                   # 格子底部 y
    center: Tuple[int, int]       # 格子中心坐标 (x, y)，可直接 tap
    height: int                   # 格子高度

    def random_point(self) -> Tuple[int, int]:
        cx, cy = self.center
        margin_y = max(1, self.height // 5)
        return (cx + random.randint(-10, 10),
                random.randint(self.top + margin_y, self.bottom - margin_y))


def detect_battle_column_cells(
    image: ImageLike,
    *,
    x_start: int,
    x_end: int,
    y_start: int,
    y_end: int,
    dark_threshold: float = 80,
    min_cell_height: int = 25,
    tap_x_center: int | None = None,
) -> List[BattleCellInfo]:
    """通过行均值亮度检测面板中的竖向格子。

    与 grid_detect.detect_right_column_cells 的区别：
    - 将扫描区域起点视为隐式边界，确保第一个格子也能被检测到
    - 不依赖扫描起点之前存在暗色分隔线
    - 支持自定义 tap 点的 x 坐标（检测用窄条带，点击用面板中心）

    Args:
        image: 截图 (960×540)
        x_start, x_end: 检测条带的 x 范围
        y_start, y_end: 扫描区域的 y 范围
        dark_threshold: 暗色分隔线的平均亮度阈值
        min_cell_height: 最小有效格子高度
        tap_x_center: 点击坐标的 x 中心（None 则使用检测条带中心）

    Returns:
        按编号排序的 BattleCellInfo 列表
    """
    img = load_image(image)
    gray = to_gray(img)

    roi = gray[y_start:y_end, x_start:x_end]
    row_avg = np.mean(roi, axis=1)

    center_x = tap_x_center if tap_x_center is not None else (x_start + x_end) // 2

    # ── 1. 找出暗色分隔带 ──
    separators: List[Tuple[int, int]] = []  # (start_y, end_y)
    in_sep = False
    sep_start = 0
    for i, avg in enumerate(row_avg):
        y = i + y_start
        if avg < dark_threshold and not in_sep:
            in_sep = True
            sep_start = y
        elif avg >= dark_threshold and in_sep:
            in_sep = False
            separators.append((sep_start, y - 1))
    if in_sep:
        separators.append((sep_start, y_end - 1))

    if not separators:
        return []

    # ── 2. 构建格子边界 ──
    boundaries: List[Tuple[int, int]] = []

    # 首格子：扫描起点 → 第一条分隔线之前
    first_sep_start = separators[0][0]
    if first_sep_start - y_start >= min_cell_height:
        pre_avg = float(np.mean(row_avg[:first_sep_start - y_start]))
        if pre_avg >= dark_threshold:
            boundaries.append((y_start, first_sep_start - 1))

    # 中间格子：相邻分隔线之间
    for i in range(len(separators) - 1):
        cell_top = separators[i][1] + 1
        cell_bottom = separators[i + 1][0] - 1
        if cell_bottom - cell_top + 1 >= min_cell_height:
            boundaries.append((cell_top, cell_bottom))

    # 末尾格子：最后一条分隔线之后（仅当区域亮度足够时）
    last_sep_end = separators[-1][1]
    remaining_start = last_sep_end + 1
    if y_end - remaining_start >= min_cell_height:
        tail_avg = float(np.mean(row_avg[remaining_start - y_start:]))
        if tail_avg >= dark_threshold:
            boundaries.append((remaining_start, y_end - 1))

    # ── 3. 转换为 BattleCellInfo ──
    cells: List[BattleCellInfo] = []
    for idx, (top, bottom) in enumerate(boundaries, 1):
        cy = (top + bottom) // 2
        cells.append(BattleCellInfo(
            index=idx,
            top=top,
            bottom=bottom,
            center=(center_x, cy),
            height=bottom - top + 1,
        ))

    return cells


def detect_battle_groups(image: ImageLike) -> List[BattleCellInfo]:
    """检测预设面板左侧的分组格子。

    Returns:
        按从上到下排序的分组格子列表，index 为分组编号 (1-indexed)
    """
    return detect_battle_column_cells(
        image,
        x_start=_GROUP_X_START,
        x_end=_GROUP_X_END,
        y_start=_GROUP_Y_START,
        y_end=_GROUP_Y_END,
        dark_threshold=_GROUP_DARK_THRESHOLD,
        min_cell_height=_GROUP_MIN_CELL_HEIGHT,
        tap_x_center=_GROUP_TAP_X_CENTER,
    )


def detect_battle_lineups(image: ImageLike) -> List[BattleCellInfo]:
    """检测预设面板右侧的阵容格子。

    使用宽条带 (x=140-330) 检测分隔线，点击坐标使用面板主区域中心 x=240。

    Returns:
        按从上到下排序的阵容格子列表，index 为阵容编号 (1-indexed)
    """
    return detect_battle_column_cells(
        image,
        x_start=_LINEUP_X_START,
        x_end=_LINEUP_X_END,
        y_start=_LINEUP_Y_START,
        y_end=_LINEUP_Y_END,
        dark_threshold=_LINEUP_DARK_THRESHOLD,
        min_cell_height=_LINEUP_MIN_CELL_HEIGHT,
        tap_x_center=_LINEUP_TAP_X_CENTER,
    )


__all__ = [
    "BattleCellInfo",
    "detect_battle_column_cells",
    "detect_battle_groups",
    "detect_battle_lineups",
]
