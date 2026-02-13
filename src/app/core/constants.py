"""
常量和枚举定义
"""
from copy import deepcopy
from enum import Enum, IntEnum


class AccountStatus(IntEnum):
    """账号状态"""
    ACTIVE = 1  # 可执行
    INVALID = 2  # 失效


class AccountProgress(str, Enum):
    """账号进度"""
    INIT = "init"  # 初始化中
    OK = "ok"  # 正常


class TaskType(str, Enum):
    """任务类型"""
    INIT = "起号"
    # --- 起号专用（一次性） ---
    INIT_COLLECT_REWARD = "起号_领取奖励"
    INIT_RENT_SHIKIGAMI = "起号_租借式神"
    # --- 起号专用（重复） ---
    INIT_NEWBIE_QUEST = "起号_新手任务"
    INIT_EXP_DUNGEON = "起号_经验副本"
    # --- 常规任务 ---
    FOSTER = "寄养"
    XUANSHANG = "悬赏"
    DELEGATE_HELP = "弥助"
    COOP = "勾协"
    EXPLORE = "探索突破"  # 合并探索和突破
    CARD_SYNTHESIS = "结界卡合成"
    COLLECT_LOGIN_GIFT = "领取登录礼包"
    COLLECT_MAIL = "领取邮件"
    CLIMB_TOWER = "爬塔"
    ADD_FRIEND = "加好友"
    FENGMO = "逢魔"
    DIGUI = "地鬼"
    DAOGUAN = "道馆"
    LIAO_SHOP = "寮商店"
    LIAO_COIN = "领取寮金币"
    DAILY_SUMMON = "每日一抽"
    WEEKLY_SHOP = "每周商店"
    MIWEN = "秘闻"
    REST = "休息"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkerRole(str, Enum):
    """Worker角色"""
    GENERAL = "general"
    COOP = "coop"
    INIT = "init"


class WorkerState(str, Enum):
    """Worker状态"""
    IDLE = "idle"
    BUSY = "busy"
    DOWN = "down"


class EmulatorState(str, Enum):
    """模拟器状态"""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


# 任务优先级配置
TASK_PRIORITY = {
    TaskType.INIT: 100,
    TaskType.INIT_COLLECT_REWARD: 99,
    TaskType.INIT_RENT_SHIKIGAMI: 98,
    TaskType.INIT_EXP_DUNGEON: 95,
    TaskType.INIT_NEWBIE_QUEST: 93,
    TaskType.ADD_FRIEND: 90,  # 加好友优先级提高，起号后优先执行
    TaskType.COOP: 80,
    TaskType.XUANSHANG: 70,
    TaskType.DELEGATE_HELP: 65,
    TaskType.FOSTER: 60,
    TaskType.COLLECT_LOGIN_GIFT: 55,  # 登录礼包（进入游戏后优先领取）
    TaskType.EXPLORE: 50,  # 探索突破
    TaskType.MIWEN: 49,
    TaskType.FENGMO: 48,
    TaskType.COLLECT_MAIL: 45,
    TaskType.DIGUI: 46,
    TaskType.DAOGUAN: 44,
    TaskType.CARD_SYNTHESIS: 40,
    TaskType.LIAO_COIN: 43,
    TaskType.LIAO_SHOP: 42,
    TaskType.DAILY_SUMMON: 38,
    TaskType.WEEKLY_SHOP: 41,
    TaskType.CLIMB_TOWER: 35,
    TaskType.REST: 20,
}

# 任务默认配置
DEFAULT_TASK_CONFIG = {
    "寄养": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",  # 默认2020年，确保起号完成后立即触发
        "fail_delay": 30,  # 失败延迟（分钟）
    },
    "悬赏": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "弥助": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",  # 默认2020年，确保起号完成后立即触发
        "fail_delay": 30,
    },
    "勾协": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",  # 默认2020年，确保起号完成后立即触发
        "fail_delay": 30,
    },
    "探索突破": {
        "enabled": True,
        "stamina_threshold": 1000,  # 体力阈值，executor 通过 OCR 检查
        "next_time": "2020-01-01 00:00",  # 时间触发
        "fail_delay": 30,
    },
    "结界卡合成": {
        "enabled": True,
        "explore_count": 0  # 探索突破执行次数，40次后触发
    },
    "加好友": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",  # 默认2020年，确保起号完成后立即触发
        "fail_delay": 30,
    },
    "领取登录礼包": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "领取邮件": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "爬塔": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "逢魔": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "地鬼": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "道馆": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "寮商店": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "buy_heisui": True,
        "buy_lanpiao": True,
        "fail_delay": 30,
    },
    "领取寮金币": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "每日一抽": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "每周商店": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "buy_lanpiao": True,
        "buy_heidan": True,
        "buy_tili": True,
        "fail_delay": 30,
    },
    "秘闻": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "签到": {
        "enabled": False,
        "status": "未签到",
        "signed_date": None
    }
}

# 起号阶段任务默认配置
DEFAULT_INIT_TASK_CONFIG = {
    # === 阶段 1：一次性前置任务 ===
    "起号_租借式神": {
        "enabled": True,
        "completed": False,
    },
    # === 阶段 2：重复任务（阶段1完成后按优先级/间隔并行调度）===
    "起号_领取奖励": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "起号_新手任务": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "起号_经验副本": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "探索突破": {
        "enabled": True,
        "stamina_threshold": 1000,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "签到": {
        "enabled": True,
        "status": "未签到",
        "signed_date": None,
    },
    "地鬼": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "每周商店": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "buy_lanpiao": True,
        "buy_heidan": True,
        "buy_tili": True,
        "fail_delay": 30,
    },
    "寮商店": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "buy_heisui": True,
        "buy_lanpiao": True,
        "fail_delay": 30,
    },
    "领取寮金币": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "领取邮件": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
    "加好友": {
        "enabled": True,
        "next_time": "2020-01-01 00:00",
        "fail_delay": 30,
    },
}

# 全局休息时间（0-6点）
GLOBAL_REST_START = "00:00"
GLOBAL_REST_END = "06:00"

# 有 fail_delay 的任务类型列表（用于全局默认延迟配置）
TASK_TYPES_WITH_FAIL_DELAY = [
    name for name, cfg in DEFAULT_TASK_CONFIG.items()
    if isinstance(cfg, dict) and "fail_delay" in cfg
]


def build_default_task_config(fail_delays: dict = None) -> dict:
    """根据全局 fail_delay 配置生成有效的 DEFAULT_TASK_CONFIG。

    Args:
        fail_delays: 来自 SystemConfig.default_fail_delays 的字典，
                     如 {"寄养": 60, "悬赏": 45}。None 或空时使用硬编码默认值。
    Returns:
        完整的 task_config 字典（深拷贝），fail_delay 字段已被覆盖。
    """
    config = deepcopy(DEFAULT_TASK_CONFIG)
    if not fail_delays:
        return config
    for task_name, delay in fail_delays.items():
        if (task_name in config
                and isinstance(config[task_name], dict)
                and "fail_delay" in config[task_name]
                and isinstance(delay, (int, float))
                and delay > 0):
            config[task_name]["fail_delay"] = int(delay)
    return config
