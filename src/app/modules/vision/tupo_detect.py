"""
结界突破 3×3 网格状态检测

检测结界突破界面中 9 个对手卡片的状态：
- DEFEATED (已击败)：卡片整体变暗（有"破"字印章覆盖），平均亮度 V 显著偏低
- FAILED (没打过)：卡片右侧有彩色旗帜标志
- NOT_CHALLENGED (未挑战)：无标志，正常明亮外观
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .template import match_template
from .utils import ImageLike, load_image


class TupoCardState(str, Enum):
    DEFEATED = "defeated"              # 已击败
    FAILED = "failed"                  # 没打过（挑战失败）
    NOT_CHALLENGED = "not_challenged"  # 未挑战


@dataclass
class TupoCard:
    """结界突破卡片状态"""
    index: int                                  # 0-8，左上到右下
    row: int                                    # 0-2
    col: int                                    # 0-2
    state: TupoCardState
    center: Tuple[int, int]                     # 卡片中心坐标（用于点击）
    roi: Tuple[int, int, int, int]              # 卡片边界框 (x, y, w, h)
    avg_v: float                                # 卡片平均亮度 V（调试用）
    failed_score: float                         # 没打过旗帜模板匹配得分


@dataclass
class TupoGridResult:
    """结界突破网格检测结果"""
    cards: List[TupoCard]
    defeated_count: int
    failed_count: int
    not_challenged_count: int

    def get_available(self) -> List[TupoCard]:
        """返回所有可挑战的卡片（没打过 + 未挑战），按 index 排序。"""
        return [c for c in self.cards
                if c.state in (TupoCardState.FAILED, TupoCardState.NOT_CHALLENGED)]

    def get_not_challenged(self) -> List[TupoCard]:
        """返回所有未挑战的卡片。"""
        return [c for c in self.cards if c.state == TupoCardState.NOT_CHALLENGED]

    def get_defeated(self) -> List[TupoCard]:
        """返回所有已击败的卡片。"""
        return [c for c in self.cards if c.state == TupoCardState.DEFEATED]

    @property
    def all_defeated(self) -> bool:
        """是否全部已击败（需要刷新）。"""
        return self.defeated_count == len(self.cards)


# ── 网格布局常量（960×540 分辨率）──

_GRID_X_START = 100      # 第一列卡片左边界
_GRID_Y_START = 65       # 第一行卡片上边界
_CARD_WIDTH = 238        # 单个卡片宽度
_CARD_HEIGHT = 120       # 单个卡片高度
_COL_STEP = 255          # 列步进（卡片宽度 + 间距 17px）
_ROW_STEP = 143          # 行步进（卡片高度 + 间距 23px）

# 没打过旗帜标志搜索区域（相对于卡片左上角）
# 旗帜在卡片右侧中部
_FAIL_ROI_X = 150
_FAIL_ROI_Y = 10
_FAIL_ROI_W = 88
_FAIL_ROI_H = 100        # 覆盖右侧中部区域

# 模板路径
_TPL_FAILED = "assets/ui/templates/tupo_failed_mark.png"

# ── 阈值 ──
# 已击败卡片亮度 V 阈值：已击败 V≈100-127，其他 V≈148-195
_DEFEATED_V_MAX = 135
# 没打过旗帜模板匹配阈值
_FAILED_THRESHOLD = 0.7


def _build_card_layouts() -> List[dict]:
    """预计算 9 个卡片的布局信息。"""
    layouts = []
    for row in range(3):
        for col in range(3):
            x = _GRID_X_START + col * _COL_STEP
            y = _GRID_Y_START + row * _ROW_STEP
            layouts.append({
                "index": row * 3 + col,
                "row": row,
                "col": col,
                "x": x,
                "y": y,
                "center": (x + _CARD_WIDTH // 2, y + _CARD_HEIGHT // 2),
                "roi": (x, y, _CARD_WIDTH, _CARD_HEIGHT),
            })
    return layouts


_CARD_LAYOUTS = _build_card_layouts()


def detect_tupo_grid(
    image: ImageLike,
    *,
    defeated_v_max: float = _DEFEATED_V_MAX,
    failed_threshold: float = _FAILED_THRESHOLD,
) -> TupoGridResult:
    """检测结界突破界面 3×3 网格中每个卡片的状态。

    算法:
      1. 计算每个卡片的平均亮度 V，V < 阈值 → DEFEATED（已击败卡片因"破"字印章整体变暗）
      2. 对非 DEFEATED 卡片的右侧区域匹配没打过旗帜模板 → FAILED
      3. 其余 → NOT_CHALLENGED

    Args:
        image: 截图（960×540 BGR 图像）
        defeated_v_max: 已击败判定的 V 值上限（低于此值为已击败）
        failed_threshold: 没打过旗帜模板匹配阈值

    Returns:
        TupoGridResult 包含 9 张卡片状态
    """
    img = load_image(image)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    cards: List[TupoCard] = []
    defeated = 0
    failed = 0
    not_challenged = 0

    for layout in _CARD_LAYOUTS:
        cx, cy = layout["x"], layout["y"]

        # ── 第一层：亮度检测已击败 ──
        card_hsv = hsv[cy:cy + _CARD_HEIGHT, cx:cx + _CARD_WIDTH]
        avg_v = float(np.mean(card_hsv[:, :, 2]))

        if avg_v <= defeated_v_max:
            state = TupoCardState.DEFEATED
            defeated += 1
            failed_score = 0.0
        else:
            # ── 第二层：模板匹配检测没打过 ──
            fail_x = cx + _FAIL_ROI_X
            fail_y = cy + _FAIL_ROI_Y
            fail_region = img[fail_y:fail_y + _FAIL_ROI_H,
                              fail_x:fail_x + _FAIL_ROI_W]

            m_failed = match_template(fail_region, _TPL_FAILED, threshold=0.0)
            failed_score = m_failed.score if m_failed else 0.0

            if failed_score >= failed_threshold:
                state = TupoCardState.FAILED
                failed += 1
            else:
                state = TupoCardState.NOT_CHALLENGED
                not_challenged += 1

        cards.append(TupoCard(
            index=layout["index"],
            row=layout["row"],
            col=layout["col"],
            state=state,
            center=layout["center"],
            roi=layout["roi"],
            avg_v=round(avg_v, 1),
            failed_score=round(failed_score, 3),
        ))

    return TupoGridResult(
        cards=cards,
        defeated_count=defeated,
        failed_count=failed,
        not_challenged_count=not_challenged,
    )


def find_best_target(image: ImageLike) -> Optional[TupoCard]:
    """找到最优挑战目标。

    优先选择未挑战的卡片，其次选择没打过的卡片。
    全部已击败时返回 None。
    """
    result = detect_tupo_grid(image)
    # 优先未挑战
    not_challenged = result.get_not_challenged()
    if not_challenged:
        return not_challenged[0]
    # 其次没打过（可以重新挑战）
    available = result.get_available()
    return available[0] if available else None


__all__ = [
    "TupoCardState",
    "TupoCard",
    "TupoGridResult",
    "detect_tupo_grid",
    "find_best_target",
]
