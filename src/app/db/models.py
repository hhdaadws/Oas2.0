"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import relationship
from .base import Base


class Email(Base):
    """邮箱账号表"""
    __tablename__ = "emails"
    
    email = Column(String(255), primary_key=True, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    game_accounts = relationship("GameAccount", back_populates="email_account")


class GameAccount(Base):
    """游戏账号表"""
    __tablename__ = "game_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    # login_id: -1 代表当前尚未生成平台登录数据，仅可通过邮箱触发起号
    # 不再强制唯一，以便同一邮箱在不同区服初始化阶段均为 -1
    login_id = Column(String(255), nullable=False, index=True)
    email_fk = Column(String(255), ForeignKey("emails.email"), nullable=True)
    zone = Column(String(50), nullable=False)
    level = Column(Integer, default=1)
    stamina = Column(Integer, default=0)
    gouyu = Column(Integer, default=0)       # 勾玉
    lanpiao = Column(Integer, default=0)     # 蓝票
    gold = Column(Integer, default=0)        # 金币
    progress = Column(String(20), default="init")  # init|ok
    status = Column(Integer, default=1)  # 1=可执行|2=失效
    current_task = Column(String(50), nullable=True)
    task_config = Column(JSON, default=dict)  # 任务配置
    lineup_config = Column(JSON, default=dict)  # 阵容分组配置
    remark = Column(String(500), nullable=True, default="")  # 备注
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    email_account = relationship("Email", back_populates="game_accounts")
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
    zone = Column(String(50), nullable=True)
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
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)
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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
