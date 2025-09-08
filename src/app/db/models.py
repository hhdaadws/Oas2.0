"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float, Text, UniqueConstraint
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
    login_id = Column(String(255), unique=True, nullable=False, index=True)
    email_fk = Column(String(255), ForeignKey("emails.email"), nullable=True)
    zone = Column(String(50), nullable=False)
    level = Column(Integer, default=1)
    stamina = Column(Integer, default=0)
    progress = Column(String(20), default="init")  # init|ok
    status = Column(Integer, default=1)  # 1=可执行|2=失效
    current_task = Column(String(50), nullable=True)
    task_config = Column(JSON, default=dict)  # 任务配置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    email_account = relationship("Email", back_populates="game_accounts")
    tasks = relationship("Task", back_populates="account")
    rest_config = relationship("AccountRestConfig", back_populates="account", uselist=False)
    rest_plans = relationship("RestPlan", back_populates="account")
    coop_pools = relationship("CoopPool", foreign_keys="CoopPool.account_id", back_populates="account")
    logs = relationship("Log", back_populates="account")


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
    """勾协池表"""
    __tablename__ = "coop_pools"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=False, index=True)
    expire_at = Column(DateTime, nullable=False)
    linked_account_id = Column(Integer, ForeignKey("game_accounts.id"), nullable=True)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    account = relationship("GameAccount", foreign_keys=[account_id], back_populates="coop_pools")
    linked_account = relationship("GameAccount", foreign_keys=[linked_account_id])


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