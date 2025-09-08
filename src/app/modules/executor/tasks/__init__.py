"""
任务实现模块
"""
from .base_task import BaseTask, TaskContext, TaskResult
from .foster import FosterTask
from .delegate import DelegateTask
from .coop import CoopTask
from .explore import ExploreTask
from .card_synthesis import CardSynthesisTask
from .add_friend import AddFriendTask

# 任务注册表
TASK_REGISTRY = {
    "寄养": FosterTask,
    "委托": DelegateTask,
    "勾协": CoopTask,
    "探索突破": ExploreTask,
    "结界卡合成": CardSynthesisTask,
    "加好友": AddFriendTask
}

__all__ = [
    "BaseTask", "TaskContext", "TaskResult", "TASK_REGISTRY",
    "FosterTask", "DelegateTask", "CoopTask", 
    "ExploreTask", "CardSynthesisTask", "AddFriendTask"
]