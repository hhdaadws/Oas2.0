"""
常量和枚举定义
"""
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
    FOSTER = "寄养"
    DELEGATE = "委托"
    COOP = "勾协"
    EXPLORE = "探索突破"  # 合并探索和突破
    CARD_SYNTHESIS = "结界卡合成"
    ADD_FRIEND = "加好友"
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
    TaskType.ADD_FRIEND: 90,  # 加好友优先级提高，起号后优先执行
    TaskType.COOP: 80,
    TaskType.DELEGATE: 70,
    TaskType.FOSTER: 60,
    TaskType.EXPLORE: 50,  # 探索突破
    TaskType.CARD_SYNTHESIS: 40,
    TaskType.REST: 20,
}

# 任务默认配置
DEFAULT_TASK_CONFIG = {
    "寄养": {
        "enabled": True,
        "next_time": "2020-01-01 00:00"  # 默认2020年，确保起号完成后立即触发
    },
    "委托": {
        "enabled": True,
        "next_time": "2020-01-01 00:00"  # 默认2020年，确保起号完成后立即触发
    },
    "勾协": {
        "enabled": True,
        "next_time": "2020-01-01 00:00"  # 默认2020年，确保起号完成后立即触发
    },
    "探索突破": {
        "enabled": True,
        "stamina_threshold": 1000  # 体力阈值，条件满足时立即触发
    },
    "结界卡合成": {
        "enabled": True,
        "explore_count": 0  # 探索突破执行次数，40次后触发
    },
    "加好友": {
        "enabled": True,
        "next_time": "2020-01-01 00:00"  # 默认2020年，确保起号完成后立即触发
    }
}

# 全局休息时间（0-6点）
GLOBAL_REST_START = "00:00"
GLOBAL_REST_END = "06:00"