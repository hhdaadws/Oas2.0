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
liao_templates = _discover_templates("liao")
shishen_templates = _discover_templates("shishen")
zhaohuan_templates = _discover_templates("zhaohuan")

# 游戏启动后出现 "进入" 按钮的界面
registry.register(UIDef(
    id="ENTER",
    tag="enter",
    templates=[TemplateDef(name="enter", path="assets/ui/templates/enter.png")],
))

# 账号失效界面（登录数据过期时出现，替代 ENTER）
registry.register(UIDef(
    id="SHIXIAO",
    tag="shixiao",
    templates=[TemplateDef(name="shixiao", path="assets/ui/templates/shixiao.png")],
))

# 庭院界面（家城），tag=jiacheng 用于识别；shangdian/tansuo 仅用于导航锚点
registry.register(UIDef(
    id="TINGYUAN",
    tag="jiacheng",
    templates=[
        TemplateDef(name="jiacheng", path="assets/ui/templates/jiacheng.png"),
        *shangdian_templates,
        *tansuo_templates,
        *liao_templates,
        TemplateDef(name="youjian", path="assets/ui/templates/youjian.png"),
        *shishen_templates,
        *zhaohuan_templates,
        TemplateDef(name="haoyou", path="assets/ui/templates/haoyou.png"),
        TemplateDef(name="xuanshang", path="assets/ui/templates/xuanshang.png"),
        TemplateDef(name="xinshou", path="assets/ui/templates/xinshou.png"),
    ],
))

# 探索页面：tag=weipai 用于识别；back 用于返回庭院的导航锚点；digui 用于导航到地鬼
registry.register(UIDef(
    id="TANSUO",
    tag="weipai",
    templates=[
        TemplateDef(name="weipai", path="assets/ui/templates/weipai.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
        TemplateDef(name="digui", path="assets/ui/templates/digui.png"),
        TemplateDef(name="miwen", path="assets/ui/templates/miwen.png"),
    ],
))

# 委派页面：tag=tag_weipai 用于识别；back 用于返回探索的导航锚点
registry.register(UIDef(
    id="WEIPAI",
    tag="tag_weipai",
    templates=[
        TemplateDef(name="tag_weipai", path="assets/ui/templates/tag_weipai.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
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

# 寮界面：tag=liaoxinxi 用于识别；liaojinbi_1/back 用于导航锚点
registry.register(UIDef(
    id="LIAO",
    tag="liaoxinxi",
    templates=[
        TemplateDef(name="liaoxinxi", path="assets/ui/templates/liaoxinxi.png"),
        TemplateDef(name="liaojinbi_1", path="assets/ui/templates/liaojinbi_1.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 寮信息界面：tag=shenshe 用于识别；xinxi 用于返回寮界面
registry.register(UIDef(
    id="LIAO_XINXI",
    tag="shenshe",
    templates=[
        TemplateDef(name="shenshe", path="assets/ui/templates/shenshe.png"),
        TemplateDef(name="xinxi", path="assets/ui/templates/xinxi.png"),
    ],
))

# 寮活动界面：tag=gongxunshangdian 用于识别；back 用于返回寮界面
registry.register(UIDef(
    id="LIAO_HUODONG",
    tag="gongxunshangdian",
    templates=[
        TemplateDef(name="gongxunshangdian", path="assets/ui/templates/gongxunshangdian.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 寮商店界面：tag=gongxunlibao 用于识别；exit 用于返回寮活动界面
registry.register(UIDef(
    id="LIAO_SHANGDIAN",
    tag="gongxunlibao",
    templates=[
        TemplateDef(name="gongxunlibao", path="assets/ui/templates/gongxunlibao.png"),
        TemplateDef(name="exit", path="assets/ui/templates/exit.png"),
    ],
))

# 邮箱界面：tag=youxiang 用于识别；exit 用于返回庭院的导航锚点
registry.register(UIDef(
    id="YOUXIANG",
    tag="youxiang",
    templates=[
        TemplateDef(name="youxiang", path="assets/ui/templates/youxiang.png"),
        TemplateDef(name="exit", path="assets/ui/templates/exit.png"),
    ],
))

# 式神界面：tag=tag_shishen_1 用于识别；back 用于返回庭院的导航锚点
registry.register(UIDef(
    id="SHISHEN",
    tag="tag_shishen_1",
    templates=[
        TemplateDef(name="tag_shishen_1", path="assets/ui/templates/tag_shishen_1.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 召唤界面：tag=tag_zhaohuan 用于识别；back 用于返回庭院的导航锚点
registry.register(UIDef(
    id="ZHAOHUAN",
    tag="tag_zhaohuan",
    templates=[
        TemplateDef(name="tag_zhaohuan", path="assets/ui/templates/tag_zhaohuan.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 好友界面：tag=tag_haoyou 用于识别；exit 用于返回庭院的导航锚点
registry.register(UIDef(
    id="HAOYOU",
    tag="tag_haoyou",
    templates=[
        TemplateDef(name="tag_haoyou", path="assets/ui/templates/tag_haoyou.png"),
        TemplateDef(name="exit", path="assets/ui/templates/exit.png"),
    ],
))

# 地鬼界面：tag=tag_digui 用于识别；back 用于返回探索的导航锚点
registry.register(UIDef(
    id="DIGUI",
    tag="tag_digui",
    templates=[
        TemplateDef(name="tag_digui", path="assets/ui/templates/tag_digui.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 秘闻界面：tag=tag_miwen 用于识别；back 用于返回探索的导航锚点
registry.register(UIDef(
    id="MIWEN",
    tag="tag_miwen",
    templates=[
        TemplateDef(name="tag_miwen", path="assets/ui/templates/tag_miwen.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

# 悬赏界面：tag=tag_xuanshang 用于识别；exit 用于返回庭院的导航锚点
registry.register(UIDef(
    id="XUANSHANG",
    tag="tag_xuanshang",
    templates=[
        TemplateDef(name="tag_xuanshang", path="assets/ui/templates/tag_xuanshang.png"),
        TemplateDef(name="yijianzhuizong", path="assets/ui/templates/yijianzhuizong.png"),
        TemplateDef(name="exit", path="assets/ui/templates/exit.png"),
    ],
))

# 新手任务界面：tag=tag_xinshou 用于识别；xinshou_yijianlingqu 用于一键领取锚点；back 用于返回庭院
registry.register(UIDef(
    id="XINSHOU",
    tag="tag_xinshou",
    templates=[
        TemplateDef(name="tag_xinshou", path="assets/ui/templates/tag_xinshou.png"),
        TemplateDef(name="xinshou_yijianlingqu", path="assets/ui/templates/xinshou_yijianlingqu.png"),
        TemplateDef(name="back", path="assets/ui/templates/back.png"),
    ],
))

__all__: list[str] = []
