"""
任务执行基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """任务执行状态"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


@dataclass
class TaskContext:
    """任务执行上下文"""
    account_id: int
    account_login_id: str
    task_type: str
    emulator_id: str
    adb_addr: str
    instance_id: int
    config: Dict[str, Any]
    
    # 执行环境
    capture_engine: Any = None
    vision_engine: Any = None
    emulator_adapter: Any = None


@dataclass
class TaskResult:
    """任务执行结果"""
    status: TaskStatus
    message: str
    duration: float
    screenshots: List[str] = None  # 截图文件路径列表
    ocr_results: List[Dict] = None  # OCR识别结果
    template_results: List[Dict] = None  # 模板匹配结果
    data: Dict[str, Any] = None  # 其他数据
    error: Optional[str] = None


class BaseTask(ABC):
    """任务执行基类"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.timeout = 300  # 默认5分钟超时
        self.retry_count = 3  # 默认重试3次
    
    @abstractmethod
    async def execute(self, context: TaskContext) -> TaskResult:
        """
        执行任务主逻辑
        
        Args:
            context: 任务执行上下文
            
        Returns:
            任务执行结果
        """
        pass
    
    @abstractmethod
    def get_required_templates(self) -> List[str]:
        """
        获取任务所需的模板文件
        
        Returns:
            模板文件名列表
        """
        pass
    
    @abstractmethod
    def get_ocr_regions(self) -> List[Tuple[int, int, int, int]]:
        """
        获取OCR识别区域
        
        Returns:
            ROI区域列表 [(x, y, width, height), ...]
        """
        pass
    
    def get_timeout(self) -> int:
        """获取任务超时时间（秒）"""
        return self.timeout
    
    def get_retry_count(self) -> int:
        """获取重试次数"""
        return self.retry_count
    
    async def pre_execute(self, context: TaskContext) -> bool:
        """
        任务执行前的准备工作
        
        Args:
            context: 任务执行上下文
            
        Returns:
            是否准备成功
        """
        # 默认实现：检查游戏是否在前台
        try:
            # 确保游戏应用在前台
            if context.emulator_adapter:
                return await context.emulator_adapter.ensure_app_foreground()
            return True
        except Exception as e:
            context.logger.error(f"任务准备失败: {str(e)}")
            return False
    
    async def post_execute(self, context: TaskContext, result: TaskResult) -> TaskResult:
        """
        任务执行后的清理工作
        
        Args:
            context: 任务执行上下文
            result: 执行结果
            
        Returns:
            处理后的结果
        """
        # 默认实现：清理截图缓存
        if context.capture_engine:
            context.capture_engine.clear_cache()
        
        return result
    
    def validate_context(self, context: TaskContext) -> bool:
        """
        验证执行上下文
        
        Args:
            context: 任务执行上下文
            
        Returns:
            是否有效
        """
        required_attrs = ['capture_engine', 'vision_engine', 'emulator_adapter']
        for attr in required_attrs:
            if not getattr(context, attr):
                return False
        return True