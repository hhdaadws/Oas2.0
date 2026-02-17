"""
执行器基类定义
"""
import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
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
        # 批次上下文：由 Worker 传入，用于同账号连续任务复用
        self.shared_adapter: Optional[Any] = None
        self.shared_ui: Optional[Any] = None
        self.skip_cleanup: bool = False
        # 弹窗处理器（懒初始化）
        self._popup_handler: Optional[Any] = None
        # 中断回调：长任务执行器可在 yield point 调用，检查并执行更高优先级任务
        # 签名: async (current_priority: int) -> list[str]
        # 返回已执行的任务类型名列表（空列表 = 无中断）
        self.interrupt_callback: Optional[Any] = None

    @property
    def popup_handler(self) -> Optional[Any]:
        """获取弹窗处理器。

        优先从 shared_ui 获取（UIManager 自带的 popup_handler），
        否则从 shared_adapter 构建新实例。
        """
        if self._popup_handler is not None:
            return self._popup_handler
        # 尝试从 UIManager 获取
        if self.shared_ui and hasattr(self.shared_ui, 'popup_handler'):
            self._popup_handler = self.shared_ui.popup_handler
            return self._popup_handler
        # 从 adapter 构建
        if self.shared_adapter:
            from ..ui.popup_handler import PopupHandler
            capture_method = "adb"
            if self.shared_ui and hasattr(self.shared_ui, 'capture_method'):
                capture_method = self.shared_ui.capture_method
            self._popup_handler = PopupHandler(
                self.shared_adapter,
                capture_method=capture_method,
            )
            return self._popup_handler
        return None

    def _wrap_async(self) -> None:
        """将 shared_adapter 包装为 AsyncEmulatorAdapter（如果尚未包装）。

        在 prepare() 开始时调用，使后续所有 adapter 操作自动走线程池。
        """
        if self.shared_adapter is None:
            return
        from ..emu.async_adapter import AsyncEmulatorAdapter
        if isinstance(self.shared_adapter, AsyncEmulatorAdapter):
            return
        self.shared_adapter = AsyncEmulatorAdapter(self.shared_adapter)
        self.logger.debug("shared_adapter 已包装为 AsyncEmulatorAdapter")

    async def _capture(self):
        """兼容同步/异步 adapter 的截图，直接返回 BGR ndarray。

        执行器内部应统一使用此方法代替 self.adapter.capture()。
        """
        adapter = getattr(self, 'adapter', None) or self.shared_adapter
        if adapter is None:
            return None
        capture_method = "adb"
        ui = getattr(self, 'ui', None)
        if ui and hasattr(ui, 'capture_method'):
            capture_method = ui.capture_method
        result = adapter.capture_ndarray(capture_method)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _detect_ui(self, image: Optional[bytes] = None):
        """兼容调用 self.ui.detect_ui()。

        执行器内部应统一使用此方法代替 self.ui.detect_ui()。
        """
        result = self.ui.detect_ui(image)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _tap(self, x: int, y: int) -> None:
        """兼容同步/异步 adapter 的 tap。"""
        adapter = getattr(self, 'adapter', None) or self.shared_adapter
        if adapter is None:
            return
        result = adapter.tap(x, y)
        if inspect.isawaitable(result):
            await result

    async def _swipe(self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300) -> None:
        """兼容同步/异步 adapter 的 swipe。"""
        adapter = getattr(self, 'adapter', None) or self.shared_adapter
        if adapter is None:
            return
        result = adapter.swipe(x1, y1, x2, y2, dur_ms)
        if inspect.isawaitable(result):
            await result

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
            # 需要传播到 worker 层的异常，不在此处捕获
            from ..ui.manager import AccountExpiredException
            from ..ui.popups import JihaoPopupException
            if isinstance(e, (AccountExpiredException, JihaoPopupException)):
                raise
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