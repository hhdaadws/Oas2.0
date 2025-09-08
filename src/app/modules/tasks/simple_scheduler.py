"""
简化的任务调度器 - 直接基于账号配置调度，无需Task对象
"""
import asyncio
from typing import Dict, Set
from datetime import datetime, timedelta
from sqlalchemy.orm.attributes import flag_modified

from ...core.logger import logger
from ...core.timeutils import (
    now_beijing, format_beijing_time, is_time_reached, 
    add_hours_to_beijing_time, get_next_fixed_time
)
from ...core.constants import (
    TaskType, DEFAULT_TASK_CONFIG
)
from ...db.base import SessionLocal
from ...db.models import GameAccount, Log
from ..executor.base import MockExecutor


class SimpleScheduler:
    """简化调度器"""
    
    def __init__(self):
        self.workers: Dict[int, MockExecutor] = {}
        self.running_accounts: Set[int] = set()  # 正在执行任务的账号ID
        self.logger = logger.bind(module="SimpleScheduler")
        self._running = False
        self._check_task = None
        
    async def start(self):
        """启动调度器"""
        if self._running:
            self.logger.warning("调度器已在运行")
            return
        
        self.logger.info("启动简化调度器...")
        self._running = True
        
        # 初始化Workers
        await self._init_workers()
        
        # 启动检查循环
        self._check_task = asyncio.create_task(self._check_loop())
        
        self.logger.info("简化调度器启动完成")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self.logger.info("停止简化调度器...")
        self._running = False
        
        # 停止检查循环
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        # 清理Workers
        self.workers.clear()
        self.running_accounts.clear()
        
        self.logger.info("简化调度器已停止")
    
    async def _init_workers(self):
        """初始化Workers"""
        for i in range(1, 4):
            self.workers[i] = MockExecutor(worker_id=i, emulator_id=i)
        self.logger.info(f"初始化 {len(self.workers)} 个Worker")
    
    def _get_idle_worker(self) -> int:
        """获取空闲Worker"""
        # 简化：假设Worker足够，直接返回第一个
        return 1
    
    async def _check_loop(self):
        """主检查循环"""
        while self._running:
            try:
                await self._check_all_accounts()
                await asyncio.sleep(10)  # 每10秒检查一次
            except Exception as e:
                self.logger.error(f"检查循环异常: {str(e)}")
                await asyncio.sleep(5)
    
    async def _check_all_accounts(self):
        """检查所有账号的任务执行条件"""
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                # 跳过正在执行任务的账号
                if account.id in self.running_accounts:
                    continue
                
                # 检查账号是否在休息
                if await self._is_account_resting(account.id):
                    continue
                
                # 检查各种任务条件
                config = account.task_config or DEFAULT_TASK_CONFIG.copy()
                
                # 1. 检查时间触发的任务
                await self._check_time_tasks(account, config, db)
                
                # 2. 检查条件触发的任务  
                await self._check_condition_tasks(account, config, db)
    
    async def _check_time_tasks(self, account: GameAccount, config: dict, db):
        """检查时间触发的任务"""
        # 寄养任务
        foster_config = config.get("寄养", {})
        if (foster_config.get("enabled", True) and 
            foster_config.get("next_time") and 
            is_time_reached(foster_config["next_time"])):
            await self._execute_account_task(account, TaskType.FOSTER, db)
            return  # 一次只执行一个任务
        
        # 委托任务
        delegate_config = config.get("委托", {})
        if (delegate_config.get("enabled", True) and 
            delegate_config.get("next_time") and 
            is_time_reached(delegate_config["next_time"])):
            await self._execute_account_task(account, TaskType.DELEGATE, db)
            return
        
        # 勾协任务
        coop_config = config.get("勾协", {})
        if (coop_config.get("enabled", True) and 
            coop_config.get("next_time") and 
            is_time_reached(coop_config["next_time"])):
            await self._execute_account_task(account, TaskType.COOP, db)
            return
        
        # 加好友任务
        friend_config = config.get("加好友", {})
        if (friend_config.get("enabled", True) and 
            friend_config.get("next_time") and 
            is_time_reached(friend_config["next_time"])):
            await self._execute_account_task(account, TaskType.ADD_FRIEND, db)
            return
    
    async def _check_condition_tasks(self, account: GameAccount, config: dict, db):
        """检查条件触发的任务（优先级：结界卡合成 > 探索突破）"""
        # 结界卡合成任务（探索次数）- 优先级更高
        card_config = config.get("结界卡合成", {})
        if card_config.get("enabled", True):
            explore_count = card_config.get("explore_count", 0)
            if explore_count >= 40:
                await self._execute_account_task(account, TaskType.CARD_SYNTHESIS, db)
                return
        
        # 探索突破任务（体力阈值）
        explore_config = config.get("探索突破", {})
        if explore_config.get("enabled", True):
            threshold = explore_config.get("stamina_threshold", 1000)
            if account.stamina >= threshold:
                await self._execute_account_task(account, TaskType.EXPLORE, db)
                return
    
    async def _execute_account_task(self, account: GameAccount, task_type: TaskType, db):
        """执行账号的指定任务"""
        if account.id in self.running_accounts:
            return
        
        # 标记账号为运行中
        self.running_accounts.add(account.id)
        
        try:
            # 任务类型映射
            task_name_map = {
                TaskType.FOSTER: "寄养",
                TaskType.DELEGATE: "委托", 
                TaskType.COOP: "勾协",
                TaskType.EXPLORE: "探索突破",
                TaskType.CARD_SYNTHESIS: "结界卡合成",
                TaskType.ADD_FRIEND: "加好友"
            }
            task_name = task_name_map.get(task_type, str(task_type))
            
            self.logger.info(f"执行任务: 账号={account.login_id}, 任务={task_name}")
            
            # 记录开始日志
            start_log = Log(
                account_id=account.id,
                type="任务",
                level="INFO",
                message=f"开始执行{task_name}任务",
                ts=datetime.utcnow()
            )
            db.add(start_log)
            db.commit()
            
            # 获取Worker执行任务（这里直接成功）
            worker = self.workers[self._get_idle_worker()]
            
            # 模拟执行（立即成功）
            await asyncio.sleep(0.1)
            success = True
            
            if success:
                # 更新账号配置
                await self._update_account_config_after_task(account, task_type, db)
                
                # 记录成功日志
                success_log = Log(
                    account_id=account.id,
                    type="任务",
                    level="INFO", 
                    message=f"{task_name}任务执行成功",
                    ts=datetime.utcnow()
                )
                db.add(success_log)
            else:
                # 记录失败日志
                fail_log = Log(
                    account_id=account.id,
                    type="任务",
                    level="ERROR",
                    message=f"{task_name}任务执行失败",
                    ts=datetime.utcnow()
                )
                db.add(fail_log)
            
            db.commit()
            
        except Exception as e:
            self.logger.error(f"执行任务异常: {str(e)}")
            error_log = Log(
                account_id=account.id,
                type="任务",
                level="ERROR",
                message=f"{task_name}任务异常: {str(e)}",
                ts=datetime.utcnow()
            )
            db.add(error_log)
            db.commit()
        
        finally:
            # 移除运行标记
            self.running_accounts.discard(account.id)
    
    async def _update_account_config_after_task(self, account: GameAccount, task_type: TaskType, db):
        """任务完成后更新账号配置"""
        config = account.task_config or DEFAULT_TASK_CONFIG.copy()
        current_time = format_beijing_time(now_beijing())
        
        if task_type == TaskType.FOSTER:
            # 寄养：+6小时
            next_time = add_hours_to_beijing_time(current_time, 6)
            config["寄养"]["next_time"] = next_time
            
        elif task_type == TaskType.ADD_FRIEND:
            # 加好友：+24小时
            next_time = add_hours_to_beijing_time(current_time, 24)
            config["加好友"]["next_time"] = next_time
            
        elif task_type == TaskType.DELEGATE:
            # 委托：下一个固定时间点
            next_time = get_next_fixed_time(current_time, ["12:00", "18:00"])
            config["委托"]["next_time"] = next_time
            
        elif task_type == TaskType.COOP:
            # 勾协：下一个固定时间点
            next_time = get_next_fixed_time(current_time, ["18:00", "21:00"])
            config["勾协"]["next_time"] = next_time
            
        elif task_type == TaskType.EXPLORE:
            # 探索突破：增加次数
            if "结界卡合成" not in config:
                config["结界卡合成"] = {"enabled": True, "explore_count": 0}
            config["结界卡合成"]["explore_count"] = config["结界卡合成"].get("explore_count", 0) + 1
            
        elif task_type == TaskType.CARD_SYNTHESIS:
            # 结界卡合成：重置次数
            if "结界卡合成" not in config:
                config["结界卡合成"] = {"enabled": True, "explore_count": 0}
            config["结界卡合成"]["explore_count"] = 0
        
        # 保存更新
        account.task_config = config
        flag_modified(account, 'task_config')
        account.updated_at = datetime.utcnow()
        db.commit()
        
        self.logger.info(f"账号配置已更新: {account.login_id}, 任务: {task_type}")
    
    async def _is_account_resting(self, account_id: int) -> bool:
        """检查账号是否在休息"""
        # 简化实现：0-6点全局休息
        current_hour = now_beijing().hour
        if 0 <= current_hour <= 6:
            return True
        
        # TODO: 实现个体休息检查
        return False
    
    def get_running_tasks(self) -> list:
        """获取正在运行的任务"""
        result = []
        with SessionLocal() as db:
            for account_id in self.running_accounts:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if account:
                    result.append({
                        "account_id": account_id,
                        "account_login_id": account.login_id,
                        "task_type": "执行中",
                        "started_at": datetime.utcnow().isoformat()
                    })
        return result
    
    def get_queue_info(self) -> list:
        """获取队列信息（简化版本：显示即将执行的任务）"""
        result = []
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            current_time = format_beijing_time(now_beijing())
            
            for account in accounts:
                if account.id in self.running_accounts:
                    continue
                
                config = account.task_config or DEFAULT_TASK_CONFIG.copy()
                
                # 检查哪些任务即将执行（30分钟内）
                for task_name, task_config in config.items():
                    if not task_config.get("enabled", True):
                        continue
                    
                    next_time = task_config.get("next_time")
                    if next_time and is_time_reached(next_time):
                        # 已到时间，即将执行
                        result.append({
                            "account_id": account.id,
                            "account_login_id": account.login_id,
                            "task_type": task_name,
                            "next_time": next_time,
                            "priority": self._get_task_priority(task_name)
                        })
                        break  # 每个账号只显示一个即将执行的任务
        
        # 按优先级排序
        result.sort(key=lambda x: x["priority"], reverse=True)
        return result[:10]  # 返回前10个
    
    def _get_task_priority(self, task_name: str) -> int:
        """获取任务优先级"""
        priority_map = {
            "加好友": 90,
            "勾协": 80,
            "委托": 70,
            "寄养": 60,
            "探索突破": 50,
            "结界卡合成": 40
        }
        return priority_map.get(task_name, 30)


# 全局实例
simple_scheduler = SimpleScheduler()