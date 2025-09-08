"""
任务队列管理
"""
import heapq
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio
from threading import Lock

from ...core.logger import logger
from ...core.constants import TaskStatus, TASK_PRIORITY
from ...db.models import Task, GameAccount


@dataclass(order=True)
class PriorityTask:
    """优先级任务包装器"""
    priority: int
    task_id: int = field(compare=False)
    account_id: int = field(compare=False)
    task_type: str = field(compare=False)
    account_login_id: str = field(compare=False)
    enqueue_time: datetime = field(default_factory=datetime.utcnow, compare=False)
    
    def __post_init__(self):
        # 优先级越小越优先（负数处理）
        self.priority = -self.priority


class TaskQueue:
    """任务队列"""
    
    def __init__(self):
        self._queue: List[PriorityTask] = []
        self._lock = Lock()
        self._task_set: set = set()  # 用于去重
        self.logger = logger.bind(module="TaskQueue")
    
    def enqueue(self, task: Task, account: GameAccount) -> bool:
        """
        添加任务到队列
        
        Args:
            task: 任务对象
            account: 账号对象
            
        Returns:
            是否成功添加
        """
        with self._lock:
            # 检查任务是否已存在
            task_key = (task.account_id, task.type)
            if task_key in self._task_set:
                self.logger.debug(f"任务已存在队列中: {task_key}")
                return False
            
            # 获取任务优先级
            priority = task.priority or TASK_PRIORITY.get(task.type, 50)
            
            # 创建优先级任务（只存储ID和基本信息）
            priority_task = PriorityTask(
                priority=priority,
                task_id=task.id,
                account_id=task.account_id,
                task_type=task.type,
                account_login_id=account.login_id
            )
            
            # 添加到队列
            heapq.heappush(self._queue, priority_task)
            self._task_set.add(task_key)
            
            self.logger.info(
                f"任务入队: 账号={account.login_id}, "
                f"类型={task.type}, 优先级={priority}"
            )
            return True
    
    def dequeue(self) -> Optional[tuple[int, int]]:
        """
        从队列取出最高优先级任务
        
        Returns:
            (task_id, account_id) 或 None
        """
        with self._lock:
            while self._queue:
                priority_task = heapq.heappop(self._queue)
                task_key = (priority_task.account_id, priority_task.task_type)
                
                # 从集合中移除
                self._task_set.discard(task_key)
                
                self.logger.info(
                    f"任务出队: 账号={priority_task.account_login_id}, "
                    f"类型={priority_task.task_type}"
                )
                return priority_task.task_id, priority_task.account_id
            
            return None
    
    def peek(self) -> Optional[tuple[Task, GameAccount]]:
        """查看队首任务但不移除"""
        with self._lock:
            if self._queue:
                priority_task = self._queue[0]
                return priority_task.task, priority_task.account
            return None
    
    def size(self) -> int:
        """获取队列大小"""
        with self._lock:
            return len(self._queue)
    
    def clear(self):
        """清空队列"""
        with self._lock:
            self._queue.clear()
            self._task_set.clear()
            self.logger.info("队列已清空")
    
    def remove_account_tasks(self, account_id: int) -> int:
        """
        移除指定账号的所有任务
        
        Args:
            account_id: 账号ID
            
        Returns:
            移除的任务数量
        """
        with self._lock:
            # 过滤出不属于该账号的任务
            new_queue = [
                pt for pt in self._queue 
                if pt.account_id != account_id
            ]
            
            removed_count = len(self._queue) - len(new_queue)
            
            if removed_count > 0:
                # 重建堆
                self._queue = new_queue
                heapq.heapify(self._queue)
                
                # 重建任务集合
                self._task_set = {
                    (pt.account_id, pt.task_type) 
                    for pt in self._queue
                }
                
                self.logger.info(f"移除账号 {account_id} 的 {removed_count} 个任务")
            
            return removed_count
    
    def get_queue_info(self) -> List[Dict[str, Any]]:
        """
        获取队列信息
        
        Returns:
            队列中所有任务的信息
        """
        with self._lock:
            result = []
            for pt in sorted(self._queue):
                result.append({
                    "task_id": pt.task_id,
                    "account_id": pt.account_id,
                    "account_login_id": pt.account_login_id,
                    "task_type": pt.task_type,
                    "priority": -pt.priority,  # 恢复原始优先级
                    "enqueue_time": pt.enqueue_time.isoformat()
                })
            return result