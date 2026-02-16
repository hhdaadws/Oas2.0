"""
式神状态配置模块

管理 init 阶段账号的关键式神状态信息。
"""
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

# 需要追踪状态的式神列表（按需扩展）
TRACKED_SHIKIGAMI = ["座敷童子"]

# 租借式神 key
RENTAL_SHIKIGAMI_KEY = "租借式神"

# 单个式神的默认状态
DEFAULT_SHIKIGAMI_STATUS = {
    "owned": False,        # 是否拥有
    "yuhun": "",           # 御魂套装名称
    "awakened": False,     # 是否已觉醒
    "star": 1,             # 星级
    "skill_2_level": 1,    # 2技能等级（1-3）
    "skill_3_level": 1,    # 3技能等级（1-3）
}


def get_default_shikigami_config() -> Dict[str, Any]:
    """返回所有追踪式神的默认配置"""
    config: Dict[str, Any] = {
        name: deepcopy(DEFAULT_SHIKIGAMI_STATUS) for name in TRACKED_SHIKIGAMI
    }
    config[RENTAL_SHIKIGAMI_KEY] = []
    return config


# ── 手动阵容配置相关常量 ──

# 租借式神在阵容配置界面底部列表的模板映射
_LINEUP_RENTAL_TEMPLATES: Dict[str, str] = {
    "阿修罗": "assets/ui/shishen/lineup_axiuluo.png",
    "古火鸟": "assets/ui/shishen/lineup_guhuoniao.png",
    "大月丸": "assets/ui/shishen/lineup_dayuewan.png",
}

# 租借式神优先级索引（同 SHIKIGAMI_CANDIDATES 顺序）
_RENTAL_PRIORITY_MAP: Dict[str, int] = {"阿修罗": 0, "古火鸟": 1, "大月丸": 2}

# 座敷童子模板
_ZUOFU_AWAKENED_TPL = "assets/ui/shishen/yijuexing_zuofu.png"
_ZUOFU_NORMAL_TPL = "assets/ui/shishen/weijuexing_zuofu.png"


def build_manual_lineup_info(
    shikigami_config: dict,
) -> Optional[Dict[str, Any]]:
    """从 shikigami_config 构建手动阵容配置所需的数据。

    Args:
        shikigami_config: GameAccount.shikigami_config JSON 字段。

    Returns:
        字典包含:
            - rental_shikigami: List[Tuple[str, str, int]]
              已按优先级排序的 (template_path, name, star)
            - zuofu_template: str | None
        数据不足时返回 None。
    """
    if not shikigami_config:
        return None

    # 1. 构建租借式神列表
    rentals_raw = shikigami_config.get(RENTAL_SHIKIGAMI_KEY, [])
    rental_with_priority: List[Tuple[str, str, int, int]] = []
    for item in rentals_raw:
        name = item.get("name", "")
        star = item.get("star", 6)
        tpl = _LINEUP_RENTAL_TEMPLATES.get(name)
        priority_idx = _RENTAL_PRIORITY_MAP.get(name, 99)
        if tpl:
            rental_with_priority.append((tpl, name, star, priority_idx))

    # 按 (star, priority_idx) 升序：5★ 优先于 6★，同星级按优先级索引
    rental_with_priority.sort(key=lambda x: (x[2], x[3]))
    sorted_rentals: List[Tuple[str, str, int]] = [
        (tpl, name, star) for tpl, name, star, _ in rental_with_priority
    ]

    # 2. 座敷童子模板
    zuofu = shikigami_config.get("座敷童子", {})
    zuofu_template: Optional[str] = None
    if zuofu.get("owned"):
        if zuofu.get("awakened"):
            zuofu_template = _ZUOFU_AWAKENED_TPL
        else:
            zuofu_template = _ZUOFU_NORMAL_TPL

    if not sorted_rentals and not zuofu_template:
        return None

    return {
        "rental_shikigami": sorted_rentals,
        "zuofu_template": zuofu_template,
    }


def merge_shikigami_with_defaults(shikigami_config: dict) -> Dict[str, Any]:
    """将用户配置与默认值合并，确保所有追踪式神都有完整配置。

    Args:
        shikigami_config: 账号现有的 shikigami_config（可能为空或部分字段缺失）。

    Returns:
        合并后的完整配置字典。
    """
    result = get_default_shikigami_config()
    if isinstance(shikigami_config, dict):
        for name in TRACKED_SHIKIGAMI:
            if name in shikigami_config and isinstance(shikigami_config[name], dict):
                result[name].update(shikigami_config[name])
        # 租借式神直接保留原值（列表类型）
        if RENTAL_SHIKIGAMI_KEY in shikigami_config:
            val = shikigami_config[RENTAL_SHIKIGAMI_KEY]
            if isinstance(val, list):
                result[RENTAL_SHIKIGAMI_KEY] = val
    return result
