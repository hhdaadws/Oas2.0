"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, JSON, Float, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import relationship
from .base import Base


class GameAccount(Base):
    """游戏账号表"""
    __tablename__ = "game_accounts"

    id = Column(Integer, primary_key=True, index=True)
    login_id = Column(String(255), nullable=False, index=True)
    level = Column(Integer, default=1)
    stamina = Column(Integer, default=0)
    gouyu = Column(Integer, default=0)       # 勾玉
    lanpiao = Column(Integer, default=0)     # 蓝票
    gold = Column(Integer, default=0)        # 金币
    gongxun = Column(Integer, default=0)     # 功勋
    xunzhang = Column(Integer, default=0)    # 勋章
    tupo_ticket = Column(Integer, default=0)  # 突破票
    fanhe_level = Column(Integer, default=1)  # 饭盒等级（1-10）
    jiuhu_level = Column(Integer, default=1)  # 酒壶等级（1-10）
    liao_level = Column(Integer, default=0)   # 寮等级（0=未知）
    progress = Column(String(20), default="init", index=True)  # init|ok
    status = Column(Integer, default=1, index=True)  # 1=active|2=invalid
    current_task = Column(String(50), nullable=True)
    task_config = Column(JSON, default=dict)  # 任务配置
    lineup_config = Column(JSON, default=dict)  # 阵容分组配置
    shikigami_config = Column(JSON, default=dict)  # 式神状态配置（init阶段）
    explore_progress = Column(JSON, default=dict)  # 探索进度（1-28章通关状态）
    remark = Column(String(500), nullable=True, default="")  # 备注
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    tasks = relationship("Task", back_populates="account")
    rest_config = relationship("AccountRestConfig", back_populates="account", uselist=False)
    rest_plans = relationship("RestPlan", back_populates="account")
    # 历史：GameAccount 作为勾协发起方的配对记录
    coop_pools = relationship(
        "CoopPool",
        foreign_keys="CoopPool.owner_account_id",
        back_populates="owner_account",
    )
    logs = relationship("Log", back_populates="account")

    # 仅对 login_id != '-1' 强制唯一
    __table_args__ = (
        Index(
            'ux_game_accounts_login_id_nonminus1',
            'login_id',
            unique=True,
            sqlite_where=text("login_id <> '-1'"),
        ),
    )


class AccountRestConfig(Base):
    """账号休息配置表"""
    __tablename__ = "account_rest_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("game_accounts.id"), unique=True, nullable=False)
    enabled = Column(Integer, default=1)  # 1=启用, 0=禁用
    mode = Column(String(20), default="random")  # random|custom
    rest_start = Column(String(10), nullable=True)  # HH:MM
    rest_duration = Column(Integer, default=2)  # 小时数
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    account = relationship("GameAccount", back_populates="rest_config")


class Task(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    priority = Column(Integer, nullable=False, index=True)
    scheduled_at = Column(DateTime, nullable=True)
    next_at = Column(DateTime, nullable=True, index=True)
    conditions = Column(JSON, default=dict)
    status = Column(String(20), default="pending", index=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    account = relationship("GameAccount", back_populates="tasks")
    task_runs = relationship("TaskRun", back_populates="task")


class CoopPool(Base):
    """勾协配对池（历史亲和与统计）"""
    __tablename__ = "coop_pools"

    id = Column(Integer, primary_key=True, index=True)
    # 发起勾协的一侧（普通游戏账号）
    owner_account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=False, index=True)
    # 被勾协的一侧（来自勾协库账号）
    coop_account_id = Column(Integer, ForeignKey("coop_accounts.id"), nullable=False, index=True)
    used_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    owner_account = relationship(
        "GameAccount",
        back_populates="coop_pools",
    )
    coop_account = relationship(
        "CoopAccount",
        back_populates="coop_pools",
    )

    __table_args__ = (
        UniqueConstraint('owner_account_id', 'coop_account_id', name='ux_coop_pair'),
    )


class CoopAccount(Base):
    """勾协账号库（仅录入ID账号）"""
    __tablename__ = "coop_accounts"

    id = Column(Integer, primary_key=True, index=True)
    login_id = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(Integer, default=1)  # 1=可用 2=失效
    expire_date = Column(String(10), nullable=True, index=True)  # YYYY-MM-DD（过期日期）
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系：作为被勾协方的配对记录
    coop_pools = relationship(
        "CoopPool",
        foreign_keys="CoopPool.coop_account_id",
        back_populates="coop_account",
    )


class CoopWindow(Base):
    """勾协时间窗用量计数（12点/18点自然分段）"""
    __tablename__ = "coop_windows"

    id = Column(Integer, primary_key=True, index=True)
    coop_account_id = Column(Integer, ForeignKey("coop_accounts.id"), nullable=False, index=True)
    window_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD（窗口起始日）
    slot = Column(Integer, nullable=False, index=True)  # 12 或 18（窗口起点）
    used_count = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('coop_account_id', 'window_date', 'slot', name='ux_coop_window_unique'),
    )


class Emulator(Base):
    """模拟器表"""
    __tablename__ = "emulators"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    role = Column(String(20), nullable=False)  # coop|general|init
    state = Column(String(20), default="stopped")
    adb_addr = Column(String(100), nullable=False)
    instance_id = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    workers = relationship("Worker", back_populates="emulator")


class Log(Base):
    """日志表"""
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=True, index=True)
    type = Column(String(50), nullable=False, index=True)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 关系
    account = relationship("GameAccount", back_populates="logs")


class Worker(Base):
    """Worker表"""
    __tablename__ = "workers"
    
    id = Column(Integer, primary_key=True, index=True)
    emulator_id = Column(Integer, ForeignKey("emulators.id"), nullable=False)
    role = Column(String(20), nullable=False)  # coop|general|init
    state = Column(String(20), default="idle")  # idle|busy|down
    last_beat = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    emulator = relationship("Emulator", back_populates="workers")
    task_runs = relationship("TaskRun", back_populates="worker")


class TaskRun(Base):
    """任务运行记录表"""
    __tablename__ = "task_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    emulator_id = Column(Integer, ForeignKey("emulators.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    error_code = Column(String(50), nullable=True)
    artifacts = Column(JSON, default=dict)
    
    # 关系
    task = relationship("Task", back_populates="task_runs")
    worker = relationship("Worker", back_populates="task_runs")
    emulator = relationship("Emulator")


class RestPlan(Base):
    """休息计划表"""
    __tablename__ = "rest_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    start_time = Column(String(10), nullable=False)  # HH:MM
    end_time = Column(String(10), nullable=False)  # HH:MM
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    account = relationship("GameAccount", back_populates="rest_plans")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('account_id', 'date', name='_account_date_uc'),
    )


class SystemConfig(Base):
    """系统配置（单行）"""
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    launch_mode = Column(String(20), default="adb_monkey")  # adb_monkey|adb_intent
    capture_method = Column(String(20), default="adb")  # adb|ipc
    adb_path = Column(String(255), default="adb")
    ipc_dll_path = Column(String(500), nullable=True)
    mumu_manager_path = Column(String(500), nullable=True)
    nemu_folder = Column(String(500), nullable=True)
    pkg_name = Column(String(200), default="com.netease.onmyoji")
    activity_name = Column(String(200), default=".MainActivity")
    python_path = Column(String(1000), nullable=True)  # 额外的 Python 模块搜索路径（分号或逗号分隔）
    pull_post_mode = Column(String(20), default="none")    # 抓取后建号模式: none|auto|confirm
    default_fail_delays = Column(JSON, nullable=True)  # 全局默认失败延迟 {"寄养": 30, ...}
    default_task_enabled = Column(JSON, nullable=True)  # 新建账号任务默认启用 {"签到": false, ...}
    global_task_switches = Column(JSON, nullable=True)  # 全局任务开关 {"召唤礼包": true}
    save_fail_screenshot = Column(Boolean, default=False)  # 任务失败时保存截图
    global_rest_enabled = Column(Boolean, default=True)  # 全局休息总开关
    default_rest_config = Column(JSON, nullable=True)  # 新建账号默认休息配置 {"enabled": false, "mode": "random", "duration": 2}
    duiyi_jingcai_answers = Column(JSON, nullable=True)  # 对弈竞猜每窗口答案 {"10:00": "左", "12:00": "右", ...}
    duiyi_reward_coord = Column(JSON, nullable=True)  # 对弈竞猜领奖点击区域 {"x1": 0, "y1": 0, "x2": 100, "y2": 100}
    cross_emulator_cache_enabled = Column(Boolean, default=False)  # 是否开启跨模拟器共享识图缓存
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
