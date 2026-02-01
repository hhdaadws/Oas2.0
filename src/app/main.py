"""
Main application entrypoint
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.logger import logger
from .core.config import settings
from .db import init_db
from .modules.web import register_routers
from .modules.executor.service import executor_service
from .modules.tasks.feeder import feeder


app = FastAPI(
    title="YYS Automation",
    description="Multi-account task scheduler",
    version="1.0.0",
    debug=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，开发环境使用
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    logger.info("starting app ...")
    init_db()
    register_routers(app)
    # Start executor and feeder
    await executor_service.start()
    await feeder.start()
    logger.info(f"app started at {settings.api_host}:{settings.api_port}")


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("shutting down ...")
    await feeder.stop()
    await executor_service.stop()
    logger.info("shutdown complete")


@app.get("/")
async def root():
    return {"message": "YYS Automation API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

