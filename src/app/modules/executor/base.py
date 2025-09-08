"""
执行器基类定义
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from ...core.logger import logger
from ...core.constants import TaskType, TaskStatus
from ...db.models import Task, GameAccount


class BaseExecutor(ABC):
    """执行器抽象基类"""
    
    def __init__(self, worker_id: int, emulator_id: int):
        self.worker_id = worker_id
        self.emulator_id = emulator_id
        self.current_task: Optional[Task] = None
        self.current_account: Optional[GameAccount] = None
        self.logger = logger.bind(worker_id=worker_id)
    
    @abstractmethod
    async def prepare(self, task: Task, account: GameAccount) -> bool:
        """
        准备执行任务
        
        Args:
            task: 要执行的任务
            account: 任务所属账号
            
        Returns:
            是否准备成功
        """
        pass
    
    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """
        执行任务
        
        Returns:
            执行结果，包含status和其他信息
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """清理资源"""
        pass
    
    async def run_task(self, task: Task, account: GameAccount) -> Dict[str, Any]:
        """
        运行任务的完整流程
        
        Args:
            task: 要执行的任务
            account: 任务所属账号
            
        Returns:
            执行结果
        """
        self.current_task = task
        self.current_account = account
        
        try:
            # 准备阶段
            self.logger.info(f"准备执行任务: {task.type}, 账号: {account.login_id}")
            if not await self.prepare(task, account):
                return {
                    "status": TaskStatus.FAILED,
                    "error": "任务准备失败",
                    "timestamp": datetime.utcnow()
                }
            
            # 执行阶段
            self.logger.info(f"开始执行任务: {task.type}")
            result = await self.execute()
            
            # 记录结果
            self.logger.info(f"任务执行完成: {result.get('status')}")
            return result
            
        except Exception as e:
            self.logger.error(f"任务执行异常: {str(e)}")
            return {
                "status": TaskStatus.FAILED,
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
        finally:
            # 清理
            await self.cleanup()
            self.current_task = None
            self.current_account = None


class MockExecutor(BaseExecutor):
    """模拟执行器（用于测试）"""
    
    async def prepare(self, task: Task, account: GameAccount) -> bool:
        """模拟准备"""
        self.logger.info(f"[模拟] 准备任务: {task.type}")
        # 模拟准备过程
        import asyncio
        await asyncio.sleep(0.5)
        return True
    
    async def execute(self) -> Dict[str, Any]:
        """模拟执行"""
        self.logger.info(f"[模拟] 执行任务: {self.current_task.type}")
        
        # 由于没有实际执行器，调度后立即完成，无需等待
        import random
        # await asyncio.sleep(0.1)  # 很短的延时模拟处理
        
        # 固定成功（因为没有实际执行）
        success = True
        
        if success:
            # 模拟更新账号资源
            result = {
                "status": TaskStatus.SUCCEEDED,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 不同任务类型返回不同的结果
            if self.current_task.type == TaskType.FOSTER:
                result["stamina_gained"] = random.randint(50, 150)
            elif self.current_task.type == TaskType.EXPLORE:
                # 探索突破合并，消耗体力并获得奖励
                result["stamina_used"] = random.randint(200, 400)
                result["rewards"] = {
                    "coin": random.randint(2000, 8000),
                    "breakthrough_count": random.randint(1, 3)
                }
            elif self.current_task.type == TaskType.ADD_FRIEND:
                result["friends_added"] = random.randint(1, 5)
            
            return result
        else:
            return {
                "status": TaskStatus.FAILED,
                "error": "模拟执行失败",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def cleanup(self):
        """模拟清理"""
        self.logger.info("[模拟] 清理资源")
        import asyncio
        await asyncio.sleep(0.1)