"""
Web API模块
"""
from fastapi import FastAPI
from .routers import accounts, tasks, dashboard, emulators


def register_routers(app: FastAPI):
    """注册所有路由"""
    app.include_router(accounts.router)
    app.include_router(tasks.router)
    app.include_router(dashboard.router)
    app.include_router(emulators.router)


__all__ = ["register_routers"]