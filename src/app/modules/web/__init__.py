"""
Web API模块
"""
from fastapi import FastAPI
from .routers import accounts, tasks, dashboard, emulators, coop
from .routers import emulators_test, system


def register_routers(app: FastAPI):
    """注册所有路由"""
    app.include_router(accounts.router)
    app.include_router(tasks.router)
    app.include_router(dashboard.router)
    app.include_router(emulators.router)
    app.include_router(coop.router)
    app.include_router(emulators_test.router)
    app.include_router(system.router)


__all__ = ["register_routers"]
