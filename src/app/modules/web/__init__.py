"""
Web API模块
"""
from fastapi import FastAPI
from .routers import accounts, tasks, dashboard, emulators, coop
from .routers import emulators_test, system, executor, account_pull, auth


def register_routers(app: FastAPI):
    """注册所有路由"""
    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(tasks.router)
    app.include_router(dashboard.router)
    app.include_router(emulators.router)
    app.include_router(coop.router)
    app.include_router(emulators_test.router)
    app.include_router(system.router)
    app.include_router(executor.router)
    app.include_router(account_pull.router)


__all__ = ["register_routers"]
