"""
弹窗定义与注册表

定义游戏中意外弹窗的检测和关闭方式。
每个弹窗包含：检测模板（判断弹窗是否出现）+ 关闭动作序列（如何关闭弹窗）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .registry import TemplateDef


class DismissType(str, Enum):
    """弹窗关闭方式"""
    TAP = "tap"                    # 点击固定坐标
    TAP_TEMPLATE = "tap_template"  # 通过模板匹配找到按钮并点击（主要方式）
    TAP_SELF = "tap_self"          # 点击弹窗检测模板自身的匹配位置
    BACK_KEY = "back_key"          # 按返回键


@dataclass
class DismissAction:
    """弹窗关闭动作"""
    type: DismissType
    # TAP 模式: 固定坐标
    tap_x: int = 0
    tap_y: int = 0
    # TAP 模式: 随机点击矩形区域 (x1, y1, x2, y2)，边界包含端点
    tap_rect: Optional[Tuple[int, int, int, int]] = None
    # TAP_TEMPLATE 模式: 按钮模板路径 + 可选 ROI + 阈值
    template_path: str = ""
    template_roi: Optional[Tuple[int, int, int, int]] = None
    template_threshold: float = 0.85
    # 动作后等待（毫秒），让 UI 完成过渡
    post_delay_ms: int = 1000
    # 点击后等待模板消失（仅 TAP_TEMPLATE 生效）
    wait_disappear: bool = False
    wait_disappear_timeout_ms: int = 5000
    wait_disappear_poll_ms: int = 500


@dataclass
class PopupDef:
    """弹窗定义

    Attributes:
        id: 唯一标识，如 "announcement"
        label: 显示名称（日志用），如 "公告弹窗"
        detect_template: 弹窗检测模板
        dismiss_actions: 关闭动作序列（按顺序执行）
        priority: 优先级，越小越先检查（常见弹窗优先级设小）
        max_dismiss_attempts: 单次处理中最大关闭尝试次数
        enabled: 是否启用
    """
    id: str
    label: str
    detect_template: TemplateDef
    dismiss_actions: List[DismissAction] = field(default_factory=list)
    priority: int = 50
    max_dismiss_attempts: int = 3
    enabled: bool = True


class PopupRegistry:
    """弹窗注册表"""

    def __init__(self) -> None:
        self._popups: Dict[str, PopupDef] = {}

    def register(self, popup: PopupDef) -> None:
        """注册弹窗定义"""
        self._popups[popup.id] = popup

    def unregister(self, popup_id: str) -> None:
        """移除弹窗定义"""
        self._popups.pop(popup_id, None)

    def get(self, popup_id: str) -> Optional[PopupDef]:
        """获取弹窗定义"""
        return self._popups.get(popup_id)

    def all_sorted(self) -> List[PopupDef]:
        """按优先级排序返回所有已启用的弹窗定义"""
        return sorted(
            (p for p in self._popups.values() if p.enabled),
            key=lambda p: p.priority,
        )


# 全局默认弹窗注册表
popup_registry = PopupRegistry()


class JihaoPopupException(Exception):
    """检测到祭号弹窗时抛出，触发关闭游戏 + 批量延后任务。"""
    pass
