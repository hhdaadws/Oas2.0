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

    r.register(PopupDef(
        id="popup_1",
        label="通用弹窗",
        detect_template=TemplateDef(
            name="popup_1",
            path="assets/ui/templates/popup_1.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_TEMPLATE,
                template_path="assets/ui/templates/exit.png",
                post_delay_ms=1000,
            ),
        ],
        priority=50,
    ))

    # NPC 剧情对话（底部深色对话框 + 跳过按钮）
    r.register(PopupDef(
        id="story_dialogue",
        label="剧情对话",
        detect_template=TemplateDef(
            name="tiaoguo",
            path="assets/ui/templates/tiaoguo.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_SELF,
                post_delay_ms=1500,
            ),
        ],
        priority=20,
    ))

    # 插画弹窗（全屏插画/过场画面，点击屏幕中心关闭）
    r.register(PopupDef(
        id="story_illustration",
        label="插画弹窗",
        detect_template=TemplateDef(
            name="chahua",
            path="assets/ui/templates/chahua.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP,
                tap_x=480,
                tap_y=270,
                post_delay_ms=1000,
            ),
        ],
        priority=25,
    ))

    # 领取成功弹窗（点击自身关闭）
    r.register(PopupDef(
        id="lingquchenggong",
        label="领取成功",
        detect_template=TemplateDef(
            name="lingquchenggong",
            path="assets/ui/templates/lingquchenggong.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_SELF,
                post_delay_ms=1500,
            ),
        ],
        priority=15,
    ))

    # 获得奖励弹窗（点击左上角关闭，多处执行器共用）
    r.register(PopupDef(
        id="jiangli",
        label="获得奖励",
        detect_template=TemplateDef(
            name="jiangli",
            path="assets/ui/templates/jiangli.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP,
                tap_x=20,
                tap_y=20,
                post_delay_ms=1500,
            ),
        ],
        priority=12,
    ))

    # 成就升级弹窗（点击左上角关闭）
    r.register(PopupDef(
        id="chengjiu_shengji",
        label="成就升级",
        detect_template=TemplateDef(
            name="chengjiu_shengji",
            path="assets/ui/templates/chengjiu_shengji.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP,
                tap_x=20,
                tap_y=20,
                post_delay_ms=1500,
            ),
        ],
        priority=13,
    ))

    # 通用弹窗2（点击自身关闭）
    r.register(PopupDef(
        id="popup_2",
        label="通用弹窗2",
        detect_template=TemplateDef(
            name="popup_2",
            path="assets/ui/templates/popup_2.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_SELF,
                post_delay_ms=1500,
            ),
        ],
        priority=50,
    ))

    # 通用弹窗3（通过关闭按钮模板关闭）
    r.register(PopupDef(
        id="popup_3",
        label="通用弹窗3",
        detect_template=TemplateDef(
            name="popup_3",
            path="assets/ui/templates/popup_3.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_TEMPLATE,
                template_path="assets/ui/templates/popup_3_close.png",
                post_delay_ms=1000,
            ),
        ],
        priority=50,
    ))

    # 通用弹窗4（通过关闭按钮模板关闭）
    r.register(PopupDef(
        id="popup_4",
        label="通用弹窗4",
        detect_template=TemplateDef(
            name="popup_4",
            path="assets/ui/templates/popup_4.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_TEMPLATE,
                template_path="assets/ui/templates/popup_4_close.png",
                post_delay_ms=1000,
            ),
        ],
        priority=50,
    ))

    # 通用弹窗5（先点击确保 popup_5_1 消失，再点取消关闭）
    r.register(PopupDef(
        id="popup_5",
        label="通用弹窗5",
        detect_template=TemplateDef(
            name="popup_5",
            path="assets/ui/templates/popup_5.png",
        ),
        dismiss_actions=[
            DismissAction(
                type=DismissType.TAP_TEMPLATE,
                template_path="assets/ui/templates/popup_5_1.png",
                post_delay_ms=500,
                wait_disappear=True,
                wait_disappear_timeout_ms=3000,
                wait_disappear_poll_ms=500,
            ),
            DismissAction(
                type=DismissType.TAP_TEMPLATE,
                template_path="assets/ui/templates/popup_5_quxiao.png",
                post_delay_ms=1000,
            ),
        ],
        priority=50,
    ))

    # 祭号弹窗（检测到后抛出异常，由 Worker 处理关闭游戏 + 批量延后）
    r.register(PopupDef(
        id="jihao",
        label="祭号弹窗",
        detect_template=TemplateDef(
            name="jihao",
            path="assets/ui/templates/jihao.png",
        ),
        dismiss_actions=[],  # 不需要关闭动作，检测到就抛异常
        priority=1,  # 最高优先级，最先检测
    ))
