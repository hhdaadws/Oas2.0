"""
阵容分组配置模块

管理各任务的分组和阵容预设选择。
"""
from copy import deepcopy
from typing import Dict

# 支持阵容配置的任务列表
LINEUP_SUPPORTED_TASKS = ["逢魔", "地鬼", "探索", "结界突破", "道馆", "秘闻", "御魂"]

# 默认阵容配置（0 表示未选择/不切换）
DEFAULT_LINEUP = {"group": 0, "position": 0}


def get_default_lineup_config() -> Dict[str, Dict[str, int]]:
    """返回所有支持任务的默认阵容配置"""
    return {task: deepcopy(DEFAULT_LINEUP) for task in LINEUP_SUPPORTED_TASKS}


def get_lineup_for_task(lineup_config: dict, task_key: str) -> Dict[str, int]:
    """获取指定任务的阵容配置，若未配置则返回默认值"""
    return lineup_config.get(task_key, deepcopy(DEFAULT_LINEUP))


def merge_lineup_with_defaults(lineup_config: dict) -> Dict[str, Dict[str, int]]:
    """将用户配置与默认值合并，确保所有支持的任务都有配置"""
    result = get_default_lineup_config()
    if isinstance(lineup_config, dict):
        for task in LINEUP_SUPPORTED_TASKS:
            if task in lineup_config and isinstance(lineup_config[task], dict):
                result[task].update(lineup_config[task])
    return result
