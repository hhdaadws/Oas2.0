# -*- coding: utf-8 -*-
"""数据库模块"""
from .base import Base, engine, SessionLocal, get_db
from .models import (
    Email, GameAccount, AccountRestConfig, Task, CoopPool,
    Emulator, Log, Worker, TaskRun, RestPlan
)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)


__all__ = [
    "Base", "engine", "SessionLocal", "get_db", "init_db",
    "Email", "GameAccount", "AccountRestConfig", "Task", "CoopPool",
    "Emulator", "Log", "Worker", "TaskRun", "RestPlan"
]