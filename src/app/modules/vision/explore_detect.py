"""
探索章节识别与挑战标志发光检测

功能:
  1. 基于 OCR 识别探索界面右侧的章节标签（第一章~第二十八章）
  2. 检测探索地图中怪物头顶挑战标志的发光状态（旋转光环 vs 普通）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .template import find_all_templates
from .grid_detect import nms_by_distance
from .utils import ImageLike, load_image
from ..ocr.recognize import ocr, Roi


@dataclass
class ChapterInfo:
    """探索章节信息"""
    number: int                      # 章节编号（1-28）
    text: str                        # OCR 原始文本（如"第二十八章"）
    center: Tuple[int, int]          # 文本中心坐标（可用于点击）
    confidence: float                # OCR 置信度


# ── 章节标签 OCR 区域（960×540 分辨率）──
# 右侧竖排章节标签区域
_CHAPTER_ROI: Roi = (830, 80, 130, 400)

# 中文数字映射
_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10,
}

# OCR 常见误识别纠错
_CORRECTION_MAP = {
    "-": "一", "—": "一", "土": "十",
}

# 章节文本匹配正则
_CHAPTER_RE = re.compile(r"第(.+?)章")


def _parse_cn_number(cn: str) -> Optional[int]:
    """解析中文数字字符串为整数（支持 1-28）。

    解析规则：
    - 单字 "一"~"九" → 1~9
    - "十" → 10
    - "十X" → 10 + X（如"十五" → 15）
    - "X十" → X * 10（如"二十" → 20）
    - "X十Y" → X * 10 + Y（如"二十八" → 28）
    """
    if not cn:
        return None

    # 应用纠错
    corrected = "".join(_CORRECTION_MAP.get(c, c) for c in cn)

    # 单字数字
    if len(corrected) == 1:
        return _CN_DIGIT.get(corrected)

    # 包含"十"的组合数字
    if "十" not in corrected:
        return None

    parts = corrected.split("十")
    if len(parts) != 2:
        return None

    left, right = parts

    # "十" → 10
    if not left and not right:
        return 10

    # "十X" → 10 + X
    if not left:
        r = _CN_DIGIT.get(right)
        return 10 + r if r is not None else None

    # "X十" → X * 10
    if not right:
        l = _CN_DIGIT.get(left)
        return l * 10 if l is not None else None

    # "X十Y" → X * 10 + Y
    l = _CN_DIGIT.get(left)
    r = _CN_DIGIT.get(right)
    if l is not None and r is not None:
        return l * 10 + r

    return None


def detect_all_visible_chapters(
    image: ImageLike,
    roi: Optional[Roi] = None,
) -> List[ChapterInfo]:
    """检测探索界面所有可见的章节标签。

    Args:
        image: 探索界面截图（960×540 BGR 图像）
        roi: 可选自定义 ROI，默认使用 _CHAPTER_ROI

    Returns:
        按 y 坐标从上到下排列的 ChapterInfo 列表
    """
    img = load_image(image)
    scan_roi = roi or _CHAPTER_ROI

    # OCR 识别右侧区域
    result = ocr(img, roi=scan_roi)

    chapters: List[ChapterInfo] = []
    for box in result.boxes:
        text = box.text.strip()
        match = _CHAPTER_RE.search(text)
        if not match:
            continue

        cn_str = match.group(1).strip()
        number = _parse_cn_number(cn_str)
        if number is not None and 1 <= number <= 28:
            chapters.append(ChapterInfo(
                number=number,
                text=text,
                center=box.center,
                confidence=box.confidence,
            ))

    # 按 y 坐标排序（从上到下）
    chapters.sort(key=lambda c: c.center[1])
    return chapters


def detect_current_chapter(
    image: ImageLike,
    roi: Optional[Roi] = None,
) -> Optional[ChapterInfo]:
    """检测探索界面当前显示的章节编号（便捷函数）。

    返回识别到的第一个章节。如果未识别到任何章节返回 None。

    Args:
        image: 探索界面截图（960×540 BGR 图像）
        roi: 可选自定义 ROI

    Returns:
        ChapterInfo 或 None
    """
    chapters = detect_all_visible_chapters(image, roi=roi)
    return chapters[0] if chapters else None


def update_explore_progress(
    account_id: int,
    chapter: int,
    difficulty: str,
) -> None:
    """更新账号的探索进度。

    Args:
        account_id: 游戏账号 ID
        chapter: 章节编号（1-28）
        difficulty: "simple" 或 "hard"
    """
    from ...db.base import SessionLocal
    from ...db.models import GameAccount
    from ...core.constants import build_default_explore_progress
    from sqlalchemy.orm.attributes import flag_modified

    if difficulty not in ("simple", "hard"):
        return
    if not (1 <= chapter <= 28):
        return

    with SessionLocal() as db:
        acc = db.query(GameAccount).filter(
            GameAccount.id == account_id
        ).first()
        if not acc:
            return

        progress = acc.explore_progress or build_default_explore_progress()
        key = str(chapter)
        if key not in progress:
            progress[key] = {"simple": False, "hard": False}

        progress[key][difficulty] = True
        acc.explore_progress = progress
        flag_modified(acc, "explore_progress")
        db.commit()


# ────────────────────────────────────────────────────
# 挑战标志发光检测
# ────────────────────────────────────────────────────


class ChallengeGlowState(str, Enum):
    """挑战标志发光状态"""
    GLOWING = "glowing"          # 发光型（有旋转光环）
    NORMAL = "normal"            # 普通型（无光环）


@dataclass
class ChallengeMarker:
    """探索地图挑战标志检测结果"""
    index: int                                    # 编号（按 y 再 x 排序）
    state: ChallengeGlowState                     # 发光状态
    center: Tuple[int, int]                        # 标志中心坐标（可用于点击）
    match_score: float                             # 模板匹配得分
    avg_v: float                                   # 环形区域平均亮度 V（调试用）
    bright_ratio: float                            # 环形区域亮像素比例（调试用）


@dataclass
class ChallengeDetectResult:
    """探索地图挑战标志批量检测结果"""
    markers: List[ChallengeMarker]
    glowing_count: int
    normal_count: int

    def get_glowing(self) -> List[ChallengeMarker]:
        """返回所有发光标志，按 index 排序。"""
        return [m for m in self.markers if m.state == ChallengeGlowState.GLOWING]

    def get_normal(self) -> List[ChallengeMarker]:
        """返回所有普通标志。"""
        return [m for m in self.markers if m.state == ChallengeGlowState.NORMAL]

    @property
    def has_glowing(self) -> bool:
        """是否存在发光标志。"""
        return self.glowing_count > 0


# ── 挑战标志检测常量 ──

# 模板路径
_TPL_CHALLENGE = "assets/ui/templates/tiaozhan.png"

# 模板匹配阈值（真标志 ~0.96，误匹配 <0.78）
_CHALLENGE_THRESHOLD = 0.85

# 环形遮罩参数（像素，相对于标志中心）
# 模板 34x32，半径≈17
_RING_INNER_RADIUS = 19     # 内圈半径（排除标志本身）
_RING_OUTER_RADIUS = 35     # 外圈半径（包含光环区域）

# 亮度分析阈值
_BRIGHT_V_THRESHOLD = 180   # "亮像素"的 V 值下限
_GLOW_BRIGHT_RATIO = 0.15   # 发光判定的亮像素比例阈值
_GLOW_AVG_V_MIN = 120       # 发光判定的平均亮度下限


def _analyze_ring_glow(
    hsv: np.ndarray,
    cx: int,
    cy: int,
    inner_r: int = _RING_INNER_RADIUS,
    outer_r: int = _RING_OUTER_RADIUS,
    bright_v_thr: int = _BRIGHT_V_THRESHOLD,
) -> Tuple[float, float]:
    """分析标志周围环形区域的亮度特征。

    在标志中心周围构建环形遮罩（内圈排除标志本身像素），
    提取 V 通道统计指标。

    Returns:
        (avg_v, bright_ratio)
    """
    h, w = hsv.shape[:2]

    # 裁剪环形区域的包围矩形
    x1 = max(0, cx - outer_r)
    y1 = max(0, cy - outer_r)
    x2 = min(w, cx + outer_r + 1)
    y2 = min(h, cy + outer_r + 1)

    roi = hsv[y1:y2, x1:x2]
    local_cx = cx - x1
    local_cy = cy - y1

    # 构建环形遮罩
    rh, rw = roi.shape[:2]
    mask = np.zeros((rh, rw), dtype=np.uint8)
    cv2.circle(mask, (local_cx, local_cy), outer_r, 255, -1)
    cv2.circle(mask, (local_cx, local_cy), inner_r, 0, -1)

    v_pixels = roi[:, :, 2][mask > 0]
    if len(v_pixels) == 0:
        return (0.0, 0.0)

    avg_v = float(np.mean(v_pixels))
    bright_ratio = float(np.sum(v_pixels >= bright_v_thr)) / len(v_pixels)
    return (avg_v, bright_ratio)


def detect_challenge_markers(
    image: ImageLike,
    *,
    template: str = _TPL_CHALLENGE,
    threshold: float = _CHALLENGE_THRESHOLD,
    inner_radius: int = _RING_INNER_RADIUS,
    outer_radius: int = _RING_OUTER_RADIUS,
    bright_v_threshold: int = _BRIGHT_V_THRESHOLD,
    glow_bright_ratio: float = _GLOW_BRIGHT_RATIO,
    glow_avg_v_min: float = _GLOW_AVG_V_MIN,
) -> ChallengeDetectResult:
    """检测探索地图中所有挑战标志及其发光状态。

    算法（两层级联）:
      1. 模板匹配定位所有挑战标志 + NMS 去重
      2. 对每个标志周围环形区域做 HSV V 通道亮度分析
      3. bright_ratio >= 阈值 且 avg_v >= 下限 → GLOWING，否则 → NORMAL

    Args:
        image: 截图（960×540 BGR 图像）
        template: 挑战标志模板路径
        threshold: 模板匹配阈值
        inner_radius: 环形遮罩内圈半径（排除标志本身）
        outer_radius: 环形遮罩外圈半径（包含光环区域）
        bright_v_threshold: 亮像素 V 值下限
        glow_bright_ratio: 发光判定的亮像素比例阈值
        glow_avg_v_min: 发光判定的平均亮度下限

    Returns:
        ChallengeDetectResult 包含所有标志及其发光状态
    """
    img = load_image(image)

    # 第一层：模板匹配 + NMS 去重
    matches = find_all_templates(img, template, threshold=threshold)
    matches = nms_by_distance(matches)

    if not matches:
        return ChallengeDetectResult(markers=[], glowing_count=0, normal_count=0)

    # 按 y 再 x 排序
    matches.sort(key=lambda m: (m.center[1], m.center[0]))

    # 第二层：环形亮度分析
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    markers: List[ChallengeMarker] = []
    glowing = 0
    normal = 0

    for i, m in enumerate(matches):
        cx, cy = m.center
        avg_v, bright_ratio = _analyze_ring_glow(
            hsv, cx, cy,
            inner_r=inner_radius,
            outer_r=outer_radius,
            bright_v_thr=bright_v_threshold,
        )

        if bright_ratio >= glow_bright_ratio and avg_v >= glow_avg_v_min:
            state = ChallengeGlowState.GLOWING
            glowing += 1
        else:
            state = ChallengeGlowState.NORMAL
            normal += 1

        markers.append(ChallengeMarker(
            index=i,
            state=state,
            center=(cx, cy),
            match_score=round(m.score, 3),
            avg_v=round(avg_v, 1),
            bright_ratio=round(bright_ratio, 3),
        ))

    return ChallengeDetectResult(
        markers=markers,
        glowing_count=glowing,
        normal_count=normal,
    )


__all__ = [
    "ChapterInfo",
    "detect_all_visible_chapters",
    "detect_current_chapter",
    "update_explore_progress",
    "ChallengeGlowState",
    "ChallengeMarker",
    "ChallengeDetectResult",
    "detect_challenge_markers",
]
