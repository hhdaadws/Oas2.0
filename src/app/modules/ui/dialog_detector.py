"""
剧情对话框检测器

通过底部区域亮度分析 + 上下对比度验证，判断当前画面是否处于对话状态。
仅用于起号（INIT）任务中自动跳过剧情对话。

检测逻辑：
1. 底部对话框区域平均亮度低于阈值 → 存在暗色遮挡
2. 上方场景区域显著亮于底部 → 排除全黑/Loading 界面
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from loguru import logger

from ..vision.region_analysis import region_mean_brightness
from ..vision.utils import ImageLike

_log = logger.bind(module="DialogDetector")


@dataclass
class DialogDetectConfig:
    """对话框检测参数（960x540 分辨率）"""

    # 底部暗色区域 ROI (x, y, w, h)，避开右下角角色立绘
    roi_bottom: Tuple[int, int, int, int] = (50, 460, 650, 70)
    # 上方场景区域 ROI，跳过顶部状态栏
    roi_top: Tuple[int, int, int, int] = (0, 50, 960, 200)
    # 底部平均亮度阈值（低于此值视为暗色区域）
    dark_threshold: float = 45.0
    # 上下亮度差阈值（大于此值才认为底部显著更暗）
    contrast_threshold: float = 30.0


DEFAULT_CONFIG = DialogDetectConfig()


def detect_dialog(
    image: ImageLike,
    config: Optional[DialogDetectConfig] = None,
) -> bool:
    """检测当前画面是否处于剧情对话状态。

    Args:
        image: 截图（path/bytes/np.ndarray）
        config: 检测参数，None 使用默认配置

    Returns:
        True 表示当前处于对话状态，需要点击跳过
    """
    cfg = config or DEFAULT_CONFIG

    # 步骤1: 底部区域亮度检测
    avg_bottom = region_mean_brightness(image, cfg.roi_bottom)
    if avg_bottom > cfg.dark_threshold:
        return False

    # 步骤2: 上下亮度对比（排除全黑画面）
    avg_top = region_mean_brightness(image, cfg.roi_top)
    contrast = avg_top - avg_bottom
    if contrast < cfg.contrast_threshold:
        _log.debug(
            "对话检测: 对比度不足 bottom={:.1f} top={:.1f} contrast={:.1f}",
            avg_bottom, avg_top, contrast,
        )
        return False

    _log.debug(
        "对话检测: 命中 bottom={:.1f} top={:.1f} contrast={:.1f}",
        avg_bottom, avg_top, contrast,
    )
    return True


__all__ = ["DialogDetectConfig", "DEFAULT_CONFIG", "detect_dialog"]
