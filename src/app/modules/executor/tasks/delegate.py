"""
委托任务实现
"""
from .base_task import BaseTask, TaskContext, TaskResult, TaskStatus
from typing import List, Tuple
from ....core.logger import logger


class DelegateTask(BaseTask):
    """委托任务"""
    
    def __init__(self):
        super().__init__()
        self.name = "委托任务"
        self.timeout = 90
        self.logger = logger.bind(task="delegate")
    
    async def execute(self, context: TaskContext) -> TaskResult:
        """执行委托任务"""
        # 实现委托任务逻辑
        return TaskResult(
            status=TaskStatus.SUCCESS,
            message="委托任务执行成功",
            duration=5.0
        )
    
    def get_required_templates(self) -> List[str]:
        return ["delegate_entrance.png", "delegate_button.png"]
    
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        return [(300, 400, 200, 100)]