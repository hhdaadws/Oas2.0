"""
式神录格子检测工具。

识别式神录界面中的竖向格子结构，并定位特定模板（如 shishen_tihuan）
在格子中从上到下的编号。支持两类格子检测：
- 左侧主网格（含 shishen_tihuan 标记的行）
- 最右侧竖向格子列（通过行均值亮度自动分割）
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .template import Match, find_all_templates
from .utils import ImageLike, load_image, to_gray

# ── 左侧主网格布局常量 (960×540) ──
GRID_ROI = (390, 102, 365, 368)  # (x, y, w, h)
ROW_PITCH = 113
ROW_SEPARATORS = [209, 322, 435]
MAX_VISIBLE_ROWS = 4

# ── 最右侧竖向格子列布局常量 ──
RIGHT_COL_X_START = 790   # 格子内部左边界
RIGHT_COL_X_END = 934     # 格子内部右边界
RIGHT_COL_Y_START = 50    # 扫描起始 y
RIGHT_COL_Y_END = 490     # 扫描结束 y
RIGHT_COL_DARK_THRESHOLD = 100  # 分隔线平均亮度阈值
RIGHT_COL_MIN_CELL_HEIGHT = 20  # 最小有效格子高度

# ── 左侧竖向标签列布局常量（玩法推荐等界面） ──
LEFT_COL_ROI = (0, 50, 150, 450)  # (x, y, w, h) OCR 扫描区域


@dataclass
class GridPosition:
    """格子位置信息（模板匹配结果）"""
    row: int       # 行号 (1-indexed, 从上到下)
    match: Match   # 原始模板匹配结果

    @property
    def center(self) -> Tuple[int, int]:
        return self.match.center

    def random_point(self, margin: float = 0.2) -> Tuple[int, int]:
        return self.match.random_point(margin)


@dataclass
class CellInfo:
    """右侧格子信息（亮度分割检测结果）"""
    index: int                    # 编号 (1-indexed, 从上到下)
    top: int                      # 格子顶部 y
    bottom: int                   # 格子底部 y
    center: Tuple[int, int]       # 格子中心坐标 (x, y)
    height: int                   # 格子高度

    def random_point(self) -> Tuple[int, int]:
        cx, cy = self.center
        margin_y = max(1, self.height // 5)
        return (cx + random.randint(-10, 10),
                random.randint(self.top + margin_y, self.bottom - margin_y))


@dataclass
class LabelCell:
    """左侧竖排标签格子（含 OCR 文字）"""
    index: int                    # 编号 (1-indexed, 从上到下)
    top: int                      # 格子顶部 y
    bottom: int                   # 格子底部 y
    center: Tuple[int, int]       # 格子中心坐标 (x, y)，可直接用于 tap
    height: int                   # 格子高度
    text: str                     # OCR 识别的文字
    confidence: float             # OCR 置信度


def nms_by_distance(
    matches: List[Match],
    min_distance: Optional[int] = None,
) -> List[Match]:
    """非极大值抑制：按 score 降序保留，移除距离过近的重复匹配。"""
    if not matches:
        return []
    if min_distance is None:
        min_distance = max(matches[0].w, matches[0].h) // 2

    kept: List[Match] = []
    min_dist_sq = min_distance * min_distance
    for m in matches:
        too_close = any(
            (m.center[0] - k.center[0]) ** 2 + (m.center[1] - k.center[1]) ** 2
            < min_dist_sq
            for k in kept
        )
        if not too_close:
            kept.append(m)
    return kept


def _y_to_row(y: int) -> int:
    """将 y 坐标映射到左侧主网格行号 (1-indexed)。"""
    row = 1
    for sep in ROW_SEPARATORS:
        if y > sep:
            row += 1
    return row


# ── 最右侧格子列检测 ──

def detect_right_column_cells(
    image: ImageLike,
    *,
    x_start: int = RIGHT_COL_X_START,
    x_end: int = RIGHT_COL_X_END,
    y_start: int = RIGHT_COL_Y_START,
    y_end: int = RIGHT_COL_Y_END,
    dark_threshold: float = RIGHT_COL_DARK_THRESHOLD,
    min_cell_height: int = RIGHT_COL_MIN_CELL_HEIGHT,
) -> List[CellInfo]:
    """通过行均值亮度检测最右侧竖向格子列。

    原理：格子之间由暗色分隔线隔开，对 ROI 内每一行计算平均亮度，
    低于阈值的连续行视为分隔线，分隔线之间的区域即为格子。

    Args:
        image: 截图 (960x540)
        x_start: 格子内部左边界 x
        x_end: 格子内部右边界 x
        y_start: 扫描起始 y
        y_end: 扫描结束 y
        dark_threshold: 判定为暗色分隔线的平均亮度阈值
        min_cell_height: 最小有效格子高度（过滤噪声）

    Returns:
        按编号排序的 CellInfo 列表
    """
    img = load_image(image)
    gray = to_gray(img)

    roi = gray[y_start:y_end, x_start:x_end]
    row_avg = np.mean(roi, axis=1)

    # 找出暗色分隔带
    separators: List[Tuple[int, int, int]] = []  # (start_y, end_y, center_y)
    in_sep = False
    sep_start = 0
    for i, avg in enumerate(row_avg):
        y = i + y_start
        if avg < dark_threshold and not in_sep:
            in_sep = True
            sep_start = y
        elif avg >= dark_threshold and in_sep:
            in_sep = False
            separators.append((sep_start, y - 1, (sep_start + y) // 2))
    if in_sep:
        separators.append((sep_start, y_end - 1, (sep_start + y_end - 1) // 2))

    # 分隔带之间的区域即为格子
    center_x = (x_start + x_end) // 2
    cells: List[CellInfo] = []
    idx = 1
    for i in range(len(separators) - 1):
        cell_top = separators[i][1] + 1
        cell_bottom = separators[i + 1][0] - 1
        cell_h = cell_bottom - cell_top + 1
        if cell_h >= min_cell_height:
            cell_cy = (cell_top + cell_bottom) // 2
            cells.append(CellInfo(
                index=idx,
                top=cell_top,
                bottom=cell_bottom,
                center=(center_x, cell_cy),
                height=cell_h,
            ))
            idx += 1

    return cells


# ── 左侧竖向标签列检测 ──

def detect_left_column_labels(
    image: ImageLike,
    *,
    roi: Tuple[int, int, int, int] = LEFT_COL_ROI,
    min_confidence: float = 0.5,
) -> List[LabelCell]:
    """通过 OCR 识别左侧竖排标签列的文字和坐标。

    直接对左侧区域执行 OCR，每个识别到的文字块转换为 LabelCell，
    center 坐标可直接用于 adapter.tap() 点击。

    Args:
        image: 截图 (960x540)
        roi: OCR 扫描区域 (x, y, w, h)
        min_confidence: OCR 最低置信度

    Returns:
        按从上到下排序的 LabelCell 列表
    """
    from ..ocr.recognize import ocr as ocr_recognize

    img = load_image(image)
    ocr_result = ocr_recognize(img, roi=roi, min_confidence=min_confidence)

    labels: List[LabelCell] = []
    for box in ocr_result.boxes:
        ys = [p[1] for p in box.box]
        top = min(ys)
        bottom = max(ys)
        labels.append(LabelCell(
            index=0,
            top=top,
            bottom=bottom,
            center=box.center,
            height=bottom - top,
            text=box.text,
            confidence=box.confidence,
        ))

    # 按 y 坐标排序（从上到下），重新编号
    labels.sort(key=lambda l: l.top)
    for i, lbl in enumerate(labels, 1):
        lbl.index = i

    return labels


# ── 左侧主网格模板匹配 ──

def find_template_in_grid(
    image: ImageLike,
    template: ImageLike,
    *,
    threshold: float = 0.80,
    nms_distance: Optional[int] = None,
) -> List[GridPosition]:
    """在式神录左侧主网格中查找模板的所有出现位置，返回格子编号。

    Args:
        image: 截图 (960x540)
        template: 要查找的模板（如 shishen_tihuan.png）
        threshold: 匹配阈值
        nms_distance: NMS 距离阈值（None 自动取模板半径）

    Returns:
        按行号排序的 GridPosition 列表
    """
    raw_matches = find_all_templates(image, template, threshold=threshold)
    unique_matches = nms_by_distance(raw_matches, nms_distance)

    gx, gy, gw, gh = GRID_ROI
    grid_matches = [
        m for m in unique_matches
        if gx <= m.center[0] <= gx + gw and gy <= m.center[1] <= gy + gh
    ]

    positions = [
        GridPosition(row=_y_to_row(m.center[1]), match=m)
        for m in grid_matches
    ]
    positions.sort(key=lambda p: p.row)
    return positions


def find_shishen_tihuan_positions(
    image: ImageLike,
    template_path: str = "assets/ui/templates/shishen_tihuan.png",
    *,
    threshold: float = 0.80,
) -> List[int]:
    """便捷函数：返回 shishen_tihuan 在左侧主网格中出现的行号列表。

    Returns:
        行号列表 (1-indexed)，如 [1, 2, 3, 4]
    """
    positions = find_template_in_grid(image, template_path, threshold=threshold)
    return [p.row for p in positions]


__all__ = [
    "GridPosition",
    "CellInfo",
    "LabelCell",
    "find_template_in_grid",
    "find_shishen_tihuan_positions",
    "detect_right_column_cells",
    "detect_left_column_labels",
    "nms_by_distance",
]
