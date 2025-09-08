"""
任务调度器核心
"""
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, time
from ...core.timeutils import (
    now_beijing, format_beijing_time, is_time_reached, 
    add_hours_to_beijing_time, get_next_fixed_time
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
import random

from ...core.logger import logger
from ...core.config import settings
from ...core.constants import (
    TaskType, TaskStatus, TASK_PRIORITY, 
    DEFAULT_TASK_CONFIG, GLOBAL_REST_START, GLOBAL_REST_END
)
from ...db.base import SessionLocal
from ...db.models import (
    Task, GameAccount, AccountRestConfig, RestPlan, 
    Worker, TaskRun, Email
)
from .queue import TaskQueue
from ..executor.base import MockExecutor


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        self.queue = TaskQueue()
        self.scheduler = AsyncIOScheduler()
        self.workers: Dict[int, MockExecutor] = {}
        self.running_tasks: Dict[int, int] = {}  # account_id -> task_id
        self.worker_tasks: Dict[int, int] = {}  # worker_id -> account_id
        self.logger = logger.bind(module="TaskScheduler")
        self._running = False
        self._dispatch_task = None
        
    async def start(self):
        """启动调度器"""
        if self._running:
            self.logger.warning("调度器已在运行")
            return
        
        self.logger.info("启动调度器...")
        self._running = True
        
        # 配置定时任务
        self._setup_scheduled_tasks()
        
        # 启动APScheduler
        self.scheduler.start()
        
        # 启动任务分发循环
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        
        # 初始化Workers（模拟）
        await self._init_workers()
        
        # 加载待执行任务
        await self._load_pending_tasks()
        
        self.logger.info("调度器启动完成")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self.logger.info("停止调度器...")
        self._running = False
        
        # 停止分发循环
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        # 停止APScheduler
        self.scheduler.shutdown()
        
        # 清理Workers
        self.workers.clear()
        
        self.logger.info("调度器已停止")
    
    def _setup_scheduled_tasks(self):
        """配置定时任务"""
        # 时间任务检查（每分钟检查一次所有基于时间的任务）
        self.scheduler.add_job(
            self._check_time_tasks,
            IntervalTrigger(minutes=1),
            id="time_check",
            name="时间任务检查"
        )
        
        # 休息计划生成（每日0点）
        self.scheduler.add_job(
            self._generate_rest_plans,
            CronTrigger(hour=0, minute=0),
            id="rest_plan",
            name="生成休息计划"
        )
        
        # 条件检查（每5分钟）
        self.scheduler.add_job(
            self._check_conditional_tasks,
            IntervalTrigger(minutes=5),
            id="condition_check",
            name="条件任务检查"
        )
    
    async def _dispatch_loop(self):
        """任务分发循环"""
        while self._running:
            try:
                # 检查是否在全局休息时间
                if self._is_global_rest_time():
                    await asyncio.sleep(60)  # 休息时间每分钟检查一次
                    continue
                
                # 获取空闲Worker
                idle_worker = self._get_idle_worker()
                if not idle_worker:
                    await asyncio.sleep(5)  # 无空闲Worker，等待
                    continue
                
                # 从队列获取任务ID
                task_tuple = self.queue.dequeue()
                if not task_tuple:
                    await asyncio.sleep(5)  # 队列为空，等待
                    continue
                
                task_id, account_id = task_tuple
                
                # 从数据库获取最新的任务和账号对象
                with SessionLocal() as db:
                    fresh_task = db.query(Task).filter(Task.id == task_id).first()
                    fresh_account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                    
                    if not fresh_task or not fresh_account:
                        self.logger.warning(f"任务或账号不存在，跳过: task_id={task_id}, account_id={account_id}")
                        continue
                    
                    # 检查任务状态是否还是PENDING
                    if fresh_task.status != TaskStatus.PENDING:
                        self.logger.info(f"任务状态已变化，跳过: {fresh_task.status}")
                        continue
                    
                    # 检查账号状态
                    if fresh_account.status != 1 or fresh_account.progress != "ok":
                        self.logger.info(f"账号状态不符合，跳过: status={fresh_account.status}, progress={fresh_account.progress}")
                        continue
                    
                    # 检查任务是否需要延后执行
                    if fresh_task.next_at and fresh_task.next_at > datetime.utcnow():
                        self.logger.info(f"任务需要延后执行，跳过: {fresh_task.next_at}")
                        # 重新入队
                        self.queue.enqueue(fresh_task, fresh_account)
                        continue
                    
                    # 检查账号是否在休息
                    if await self._is_account_resting(fresh_account.id):
                        self.logger.info(f"账号 {fresh_account.login_id} 正在休息，跳过任务")
                        # 任务重新入队，延后执行
                        fresh_task.next_at = datetime.utcnow() + timedelta(minutes=30)
                        db.commit()
                        self.queue.enqueue(fresh_task, fresh_account)
                        continue
                    
                    # 检查账号是否有正在执行的任务
                    if fresh_account.id in self.running_tasks:
                        self.logger.info(f"账号 {fresh_account.login_id} 有任务正在执行，重新入队")
                        self.queue.enqueue(fresh_task, fresh_account)
                        await asyncio.sleep(1)
                        continue
                    
                    # 分发任务
                    asyncio.create_task(self._execute_task(idle_worker, fresh_task, fresh_account))
                
            except Exception as e:
                self.logger.error(f"分发循环异常: {str(e)}")
                await asyncio.sleep(5)
    
    async def _execute_task(self, worker_id: int, task: Task, account: GameAccount):
        """
        执行任务
        
        Args:
            worker_id: Worker ID
            task: 任务对象
            account: 账号对象
        """
        executor = self.workers[worker_id]
        
        # 标记任务开始
        self.running_tasks[account.id] = task.id
        self.worker_tasks[worker_id] = account.id
        
        # 更新任务状态
        with SessionLocal() as db:
            db_task = db.query(Task).filter(Task.id == task.id).first()
            if db_task:
                db_task.status = TaskStatus.RUNNING
                db.commit()
            
            # 创建TaskRun记录
            task_run = TaskRun(
                task_id=task.id,
                worker_id=worker_id,
                emulator_id=1,  # 模拟
                started_at=datetime.utcnow(),
                status=TaskStatus.RUNNING
            )
            db.add(task_run)
            db.commit()
            run_id = task_run.id
        
        try:
            # 执行任务
            result = await executor.run_task(task, account)
            
            # 更新任务状态
            with SessionLocal() as db:
                db_task = db.query(Task).filter(Task.id == task.id).first()
                if db_task:
                    db_task.status = result["status"]
                    db_task.updated_at = datetime.utcnow()
                    
                    # 根据任务类型更新账号配置中的next_time
                    if result["status"] == TaskStatus.SUCCEEDED:
                        try:
                            account_obj = db.query(GameAccount).filter(GameAccount.id == account.id).first()
                            self.logger.info(f"任务完成，准备更新账号配置: 账号ID={account.id}, 任务类型={task.type}")
                            if account_obj:
                                config = account_obj.task_config or DEFAULT_TASK_CONFIG.copy()
                                
                                if task.type == TaskType.FOSTER:
                                    # 寄养任务：从完成时间往后6小时
                                    complete_time = format_beijing_time(now_beijing())
                                    next_time_str = add_hours_to_beijing_time(complete_time, 6)
                                    if "寄养" not in config:
                                        config["寄养"] = {"enabled": True}
                                    config["寄养"]["next_time"] = next_time_str
                                    
                                elif task.type == TaskType.ADD_FRIEND:
                                    # 加好友任务：从完成时间往后24小时
                                    complete_time = format_beijing_time(now_beijing())
                                    next_time_str = add_hours_to_beijing_time(complete_time, 24)
                                    if "加好友" not in config:
                                        config["加好友"] = {"enabled": True}
                                    config["加好友"]["next_time"] = next_time_str
                                    
                                elif task.type == TaskType.DELEGATE:
                                    # 委托任务：基于完成时间确定下一个固定时间点12:00, 18:00
                                    complete_time = format_beijing_time(now_beijing())
                                    next_time_str = get_next_fixed_time(complete_time, ["12:00", "18:00"])
                                    if "委托" not in config:
                                        config["委托"] = {"enabled": True}
                                    config["委托"]["next_time"] = next_time_str
                                    
                                elif task.type == TaskType.COOP:
                                    # 勾协任务：基于完成时间确定下一个固定时间点18:00, 21:00
                                    complete_time = format_beijing_time(now_beijing())
                                    next_time_str = get_next_fixed_time(complete_time, ["18:00", "21:00"])
                                    if "勾协" not in config:
                                        config["勾协"] = {"enabled": True}
                                    config["勾协"]["next_time"] = next_time_str
                                    
                                elif task.type == TaskType.EXPLORE:
                                    # 探索突破任务完成，增加执行次数
                                    if "结界卡合成" not in config:
                                        config["结界卡合成"] = {"enabled": True, "explore_count": 0}
                                    config["结界卡合成"]["explore_count"] = config["结界卡合成"].get("explore_count", 0) + 1
                                    self.logger.info(f"账号 {account_obj.login_id} 探索突破次数: {config['结界卡合成']['explore_count']}")
                                    
                                elif task.type == TaskType.CARD_SYNTHESIS:
                                    # 结界卡合成任务完成，重置探索次数
                                    if "结界卡合成" not in config:
                                        config["结界卡合成"] = {"enabled": True, "explore_count": 0}
                                    config["结界卡合成"]["explore_count"] = 0
                                    self.logger.info(f"账号 {account_obj.login_id} 结界卡合成完成，探索次数已重置")
                                
                                # 保存更新后的配置
                                account_obj.task_config = config
                                flag_modified(account_obj, 'task_config')  # 标记JSON字段为已修改
                                account_obj.updated_at = datetime.utcnow()
                                db.commit()  # 立即提交配置更新
                                self.logger.info(f"账号配置已更新: 账号ID={account.id}, 新配置={config}")
                        except Exception as config_error:
                            self.logger.error(f"更新账号配置失败: {str(config_error)}")
                
                # 更新TaskRun
                db_run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
                if db_run:
                    db_run.finished_at = datetime.utcnow()
                    db_run.status = result["status"]
                    # 序列化artifacts，转换枚举为字符串
                    artifacts = dict(result)
                    if "status" in artifacts:
                        artifacts["status"] = artifacts["status"].value if hasattr(artifacts["status"], "value") else artifacts["status"]
                    db_run.artifacts = artifacts
                
                db.commit()
            
            self.logger.info(f"任务执行完成: {task.type}, 状态: {result['status']}")
            
        except Exception as e:
            self.logger.error(f"任务执行异常: {str(e)}")
            
            # 更新失败状态
            with SessionLocal() as db:
                db_task = db.query(Task).filter(Task.id == task.id).first()
                if db_task:
                    db_task.status = TaskStatus.FAILED
                    db_task.retry_count += 1
                    db.commit()
        
        finally:
            # 移除运行标记
            self.running_tasks.pop(account.id, None)
            self.worker_tasks.pop(worker_id, None)
    
    async def _init_workers(self):
        """初始化Workers（模拟）"""
        # 模拟创建3个Worker
        for i in range(1, 4):
            self.workers[i] = MockExecutor(worker_id=i, emulator_id=i)
        self.logger.info(f"初始化 {len(self.workers)} 个Worker")
    
    def _get_idle_worker(self) -> Optional[int]:
        """获取空闲Worker"""
        # 查找没有在运行任务的Worker
        for worker_id in self.workers:
            if worker_id not in self.worker_tasks:
                return worker_id
        return None
    
    async def _load_pending_tasks(self):
        """加载待执行任务"""
        with SessionLocal() as db:
            # 查询所有待执行任务
            tasks = db.query(Task).filter(
                Task.status.in_([TaskStatus.PENDING])
            ).all()
            
            for task in tasks:
                account = db.query(GameAccount).filter(
                    GameAccount.id == task.account_id
                ).first()
                
                if account and account.status == 1:
                    self.queue.enqueue(task, account)
                    self.logger.info(f"入队任务: ID={task.id}, 类型={task.type}, 账号={account.login_id}")
                else:
                    self.logger.info(f"跳过任务: ID={task.id}, 账号状态={account.status if account else 'None'}")
            
            self.logger.info(f"加载 {len(tasks)} 个待执行任务")
    
    async def _check_time_tasks(self):
        """检查基于时间的任务（寄养、委托、勾协、加好友）"""
        current_time_str = format_beijing_time(now_beijing())
        
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                config = account.task_config or DEFAULT_TASK_CONFIG.copy()
                
                # 检查寄养任务
                foster_config = config.get("寄养", {})
                if (foster_config.get("enabled", True) and 
                    foster_config.get("next_time") and 
                    is_time_reached(foster_config["next_time"])):
                    
                    existing = db.query(Task).filter(
                        Task.account_id == account.id,
                        Task.type == TaskType.FOSTER,
                        Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                    ).first()
                    
                    if not existing:
                        task = Task(
                            account_id=account.id,
                            type=TaskType.FOSTER,
                            priority=TASK_PRIORITY[TaskType.FOSTER],
                            status=TaskStatus.PENDING,
                            next_at=datetime.utcnow()
                        )
                        db.add(task)
                        db.commit()
                        self.queue.enqueue(task, account)
                        self.logger.info(f"创建寄养任务: 账号 {account.login_id}")

                # 检查委托任务
                delegate_config = config.get("委托", {})
                if (delegate_config.get("enabled", True) and 
                    delegate_config.get("next_time") and 
                    is_time_reached(delegate_config["next_time"])):
                    
                    existing = db.query(Task).filter(
                        Task.account_id == account.id,
                        Task.type == TaskType.DELEGATE,
                        Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                    ).first()
                    
                    if not existing:
                        task = Task(
                            account_id=account.id,
                            type=TaskType.DELEGATE,
                            priority=TASK_PRIORITY[TaskType.DELEGATE],
                            status=TaskStatus.PENDING,
                            next_at=datetime.utcnow()
                        )
                        db.add(task)
                        db.commit()
                        self.queue.enqueue(task, account)
                        self.logger.info(f"创建委托任务: 账号 {account.login_id}")

                # 检查勾协任务
                coop_config = config.get("勾协", {})
                if (coop_config.get("enabled", True) and 
                    coop_config.get("next_time") and 
                    is_time_reached(coop_config["next_time"])):
                    
                    existing = db.query(Task).filter(
                        Task.account_id == account.id,
                        Task.type == TaskType.COOP,
                        Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                    ).first()
                    
                    if not existing:
                        task = Task(
                            account_id=account.id,
                            type=TaskType.COOP,
                            priority=TASK_PRIORITY[TaskType.COOP],
                            status=TaskStatus.PENDING,
                            next_at=datetime.utcnow() - timedelta(minutes=10)  # 提前10分钟
                        )
                        db.add(task)
                        db.commit()
                        self.queue.enqueue(task, account)
                        self.logger.info(f"创建勾协任务: 账号 {account.login_id}")

                # 检查加好友任务
                friend_config = config.get("加好友", {})
                if (friend_config.get("enabled", True) and 
                    friend_config.get("next_time") and 
                    is_time_reached(friend_config["next_time"])):
                    
                    existing = db.query(Task).filter(
                        Task.account_id == account.id,
                        Task.type == TaskType.ADD_FRIEND,
                        Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                    ).first()
                    
                    if not existing:
                        task = Task(
                            account_id=account.id,
                            type=TaskType.ADD_FRIEND,
                            priority=TASK_PRIORITY[TaskType.ADD_FRIEND],
                            status=TaskStatus.PENDING,
                            next_at=datetime.utcnow()
                        )
                        db.add(task)
                        db.commit()
                        self.queue.enqueue(task, account)
                        self.logger.info(f"创建加好友任务: 账号 {account.login_id}")

    async def _schedule_foster_tasks(self):
        """调度寄养任务"""
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                # 检查任务配置
                config = account.task_config or DEFAULT_TASK_CONFIG
                if not config.get("寄养", {}).get("enabled", True):
                    continue
                
                # 检查是否有现存任务
                existing = db.query(Task).filter(
                    Task.account_id == account.id,
                    Task.type == TaskType.FOSTER,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                ).first()
                
                if not existing:
                    # 创建任务
                    task = Task(
                        account_id=account.id,
                        type=TaskType.FOSTER,
                        priority=TASK_PRIORITY[TaskType.FOSTER],
                        status=TaskStatus.PENDING,
                        next_at=datetime.utcnow()
                    )
                    db.add(task)
                    db.commit()
                    
                    self.queue.enqueue(task, account)
    
    async def _schedule_delegate_tasks(self):
        """调度委托任务"""
        created_count = 0
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                # 检查任务配置
                config = account.task_config or DEFAULT_TASK_CONFIG
                if not config.get("委托", {}).get("enabled", True):
                    continue
                
                # 检查是否已有今日委托任务
                existing = db.query(Task).filter(
                    Task.account_id == account.id,
                    Task.type == TaskType.DELEGATE,
                    Task.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                ).first()
                
                if existing:
                    continue
                
                # 创建任务
                task = Task(
                    account_id=account.id,
                    type=TaskType.DELEGATE,
                    priority=TASK_PRIORITY[TaskType.DELEGATE],
                    status=TaskStatus.PENDING,
                    next_at=datetime.utcnow()
                )
                db.add(task)
                db.commit()
                
                # 立即加入队列
                self.queue.enqueue(task, account)
                created_count += 1
            
            self.logger.info(f"创建 {created_count} 个委托任务")
    
    async def _schedule_coop_tasks(self):
        """调度勾协任务"""
        created_count = 0
        with SessionLocal() as db:
            # 获取所有启用勾协的账号
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                # 检查任务配置
                config = account.task_config or DEFAULT_TASK_CONFIG
                if not config.get("勾协", {}).get("enabled", True):
                    continue
                
                # 检查是否已有今日勾协任务
                existing = db.query(Task).filter(
                    Task.account_id == account.id,
                    Task.type == TaskType.COOP,
                    Task.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                ).first()
                
                if existing:
                    continue
                
                # 创建勾协任务（提前10分钟执行）
                task = Task(
                    account_id=account.id,
                    type=TaskType.COOP,
                    priority=TASK_PRIORITY[TaskType.COOP],
                    status=TaskStatus.PENDING,
                    next_at=datetime.utcnow() - timedelta(minutes=10)  # 提前10分钟
                )
                db.add(task)
                db.commit()
                
                # 立即加入队列
                self.queue.enqueue(task, account)
                created_count += 1
            
            self.logger.info(f"创建 {created_count} 个勾协任务")
    
    async def _check_conditional_tasks(self):
        """检查条件触发任务（探索突破、结界卡合成）"""
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1,
                GameAccount.progress == "ok"
            ).all()
            
            for account in accounts:
                config = account.task_config or DEFAULT_TASK_CONFIG.copy()
                
                # 检查探索突破条件（体力阈值）
                explore_config = config.get("探索突破", {})
                if explore_config.get("enabled", True):
                    stamina_threshold = explore_config.get("stamina_threshold", 1000)
                    if account.stamina >= stamina_threshold:
                        existing = db.query(Task).filter(
                            Task.account_id == account.id,
                            Task.type == TaskType.EXPLORE,
                            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                        ).first()
                        
                        if not existing:
                            task = Task(
                                account_id=account.id,
                                type=TaskType.EXPLORE,
                                priority=TASK_PRIORITY[TaskType.EXPLORE],
                                status=TaskStatus.PENDING,
                                next_at=datetime.utcnow(),
                                conditions={"stamina_threshold": stamina_threshold}
                            )
                            db.add(task)
                            db.commit()
                            self.queue.enqueue(task, account)
                            self.logger.info(f"创建探索突破任务: 账号 {account.login_id}, 体力: {account.stamina}")
                
                # 检查结界卡合成条件（探索突破执行次数>=40）
                card_config = config.get("结界卡合成", {})
                if card_config.get("enabled", True):
                    explore_count = card_config.get("explore_count", 0)
                    if explore_count >= 40:
                        existing = db.query(Task).filter(
                            Task.account_id == account.id,
                            Task.type == TaskType.CARD_SYNTHESIS,
                            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                        ).first()
                        
                        if not existing:
                            task = Task(
                                account_id=account.id,
                                type=TaskType.CARD_SYNTHESIS,
                                priority=TASK_PRIORITY[TaskType.CARD_SYNTHESIS],
                                status=TaskStatus.PENDING,
                                next_at=datetime.utcnow(),
                                conditions={"explore_count": explore_count}
                            )
                            db.add(task)
                            db.commit()
                            self.queue.enqueue(task, account)
                            self.logger.info(f"创建结界卡合成任务: 账号 {account.login_id}, 探索次数: {explore_count}")
    
    async def _generate_rest_plans(self):
        """生成每日休息计划"""
        today = datetime.now().date().isoformat()
        
        with SessionLocal() as db:
            accounts = db.query(GameAccount).filter(
                GameAccount.status == 1
            ).all()
            
            for account in accounts:
                # 检查是否已有今日计划
                existing = db.query(RestPlan).filter(
                    RestPlan.account_id == account.id,
                    RestPlan.date == today
                ).first()
                
                if existing:
                    continue
                
                # 获取休息配置
                rest_config = db.query(AccountRestConfig).filter(
                    AccountRestConfig.account_id == account.id
                ).first()
                
                if rest_config and rest_config.mode == "custom":
                    # 使用自定义配置
                    start_time = rest_config.rest_start
                    duration = rest_config.rest_duration
                else:
                    # 随机生成2-3小时
                    duration = random.uniform(2, 3)
                    start_hour = random.randint(7, 20)  # 7:00-20:00之间开始
                    start_time = f"{start_hour:02d}:{random.randint(0, 59):02d}"
                
                # 计算结束时间
                start_dt = datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
                end_dt = start_dt + timedelta(hours=duration)
                end_time = end_dt.strftime("%H:%M")
                
                # 创建计划
                plan = RestPlan(
                    account_id=account.id,
                    date=today,
                    start_time=start_time,
                    end_time=end_time
                )
                db.add(plan)
            
            db.commit()
            self.logger.info(f"生成 {len(accounts)} 个账号的休息计划")
    
    def _is_global_rest_time(self) -> bool:
        """检查是否在全局休息时间"""
        now = datetime.now().time()
        start = time.fromisoformat(GLOBAL_REST_START)
        end = time.fromisoformat(GLOBAL_REST_END)
        
        # 处理跨天的情况
        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end
    
    async def _is_account_resting(self, account_id: int) -> bool:
        """检查账号是否在休息"""
        today = datetime.now().date().isoformat()
        now_time = datetime.now().time()
        
        with SessionLocal() as db:
            plan = db.query(RestPlan).filter(
                RestPlan.account_id == account_id,
                RestPlan.date == today
            ).first()
            
            if plan:
                start = time.fromisoformat(plan.start_time)
                end = time.fromisoformat(plan.end_time)
                
                if start <= end:
                    return start <= now_time <= end
                else:
                    return now_time >= start or now_time <= end
        
        return False
    
    async def create_init_task(self, email: str):
        """
        创建起号任务
        
        Args:
            email: 邮箱地址
        """
        with SessionLocal() as db:
            # 查询邮箱账号
            email_account = db.query(Email).filter(Email.email == email).first()
            if not email_account:
                self.logger.error(f"邮箱账号不存在: {email}")
                return
            
            # 为每个区服创建起号任务
            for idx, zone in enumerate(settings.zones):
                # 创建游戏账号
                login_id = f"{email}_{zone}"  # 临时login_id，执行器会更新
                
                account = GameAccount(
                    login_id=login_id,
                    email_fk=email,
                    zone=zone,
                    progress="init",
                    status=1,
                    task_config=DEFAULT_TASK_CONFIG
                )
                db.add(account)
                db.commit()
                
                # 创建起号任务
                task = Task(
                    account_id=account.id,
                    type=TaskType.INIT,
                    priority=TASK_PRIORITY[TaskType.INIT],
                    status=TaskStatus.PENDING,
                    next_at=datetime.utcnow() + timedelta(seconds=idx * 10)  # 错开执行
                )
                db.add(task)
                db.commit()
                
                self.queue.enqueue(task, account)
            
            self.logger.info(f"创建邮箱 {email} 的起号任务")


# 全局调度器实例
scheduler = TaskScheduler()