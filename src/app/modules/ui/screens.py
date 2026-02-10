"""
游戏界面定义注册。

导入本模块即可将所有界面注册到全局 registry 中。
每个界面通过 tag 字段指定唯一识别模板，其余模板仅用于锚点提取（导航点击坐标）。
"""
from __future__ import annotations

from pathlib import Path

from .registry import UIDef, TemplateDef, registry


def _discover_templates(prefix: str) -> list[TemplateDef]:
    """自动发现 {prefix}_x 系列模板（如 tansuo_1.png、shangdian_1.png）。"""
    templates_dir = Path("assets/ui/templates")
    items: list[TemplateDef] = []
    for template_path in sorted(templates_dir.glob(f"{prefix}_*.png")):
        items.append(
            TemplateDef(
                name=template_path.stem,
                path=template_path.as_posix(),
            )
        )
    # 兼容兜底：即使 glob 未命中，也保留 {prefix}_1 约定路径
    if not items:
        items.append(TemplateDef(name=f"{prefix}_1", path=f"assets/ui/templates/{prefix}_1.png"))
    return items


tansuo_templates = _discover_templates("tansuo")
shangdian_templates = _discover_templates("shangdian")

# 游戏启动后出现 "进入" 按钮的界面
registry.register(UIDef(
    id="ENTER",
    tag="enter",
    templates=[TemplateDef(name="enter", path="assets/ui/templates/enter.png")],
))

# 庭院界面（家城），tag=jiacheng 用于识别；shangdian/tansuo 仅用于导航锚点
registry.register(UIDef(
    id="TINGYUAN",
    tag="jiacheng",
    templates=[
        TemplateDef(name="jiacheng", path="assets/ui/templates/jiacheng.png"),
        *shangdian_templates,
        *tansuo_templates,
    ],
))

# 探索页面：tag=weipai 用于识别；back 用于返回庭院的导航锚点
registry.register(UIDef(
    id="TANSUO",
    tag="weipai",
    templates=[
        TemplateDef(name="weipai", path="assets/ui/templates/weipai.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 委派页面：tag=tag_weipai 用于识别
registry.register(UIDef(
    id="WEIPAI",
    tag="tag_weipai",
    templates=[TemplateDef(name="tag_weipai", path="assets/ui/templates/tag_weipai.png")],
))

# 商店界面：tag=libaowu 用于识别；back 用于返回庭院的导航锚点
registry.register(UIDef(
    id="SHANGDIAN",
    tag="libaowu",
    templates=[
        TemplateDef(name="libaowu", path="assets/ui/templates/libaowu.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

__all__: list[str] = []
