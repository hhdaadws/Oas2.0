"""
默认弹窗注册

在此文件中注册游戏中已知的弹窗定义。
框架阶段暂无具体弹窗，后续截图分析后逐个添加。
"""
from __future__ import annotations

from typing import Optional

from .popups import (
    DismissAction,
    DismissType,
    PopupDef,
    PopupRegistry,
    popup_registry,
)
from .registry import TemplateDef


def register_default_popups(reg: Optional[PopupRegistry] = None) -> None:
    """注册游戏中已知弹窗。

    添加新弹窗步骤：
    1. 截取弹窗截图，裁剪出弹窗特征区域保存为模板
       例: assets/ui/templates/popup_xxx.png
    2. 截取弹窗的关闭按钮保存为模板
       例: assets/ui/templates/popup_xxx_close.png
    3. 在此函数中调用 r.register(PopupDef(...))

    示例::

        r.register(PopupDef(
            id="announcement",
            label="公告弹窗",
            detect_template=TemplateDef(
                name="popup_announcement",
                path="assets/ui/templates/popup_announcement.png",
            ),
            dismiss_actions=[
                DismissAction(
                    type=DismissType.TAP_TEMPLATE,
                    template_path="assets/ui/templates/popup_announcement_close.png",
                    post_delay_ms=1000,
                ),
            ],
            priority=10,
        ))
    """
    r = reg or popup_registry

    # 后续在此添加具体弹窗定义
    # r.register(PopupDef(...))
