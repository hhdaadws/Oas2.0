"""
主程序入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.logger import logger
from .core.config import settings
from .db import init_db
from .modules.web import register_routers
from .modules.tasks.simple_scheduler import simple_scheduler

# 创建FastAPI应用
app = FastAPI(
    title="阴阳师自动化调度系统",
    description="多账号任务调度管理系统",
    version="1.0.0",
    debug=True,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    # 明确允许本地前端来源，避免带凭据时与通配符的冲突
    allow_origins=[
        "http://localhost:9000",
        "http://127.0.0.1:9000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """应用启动事件"""
    logger.info("应用启动中...")
    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")
    
    # 注册路由
    register_routers(app)
    logger.info("路由注册完成")
    
    # 启动调度器
    await simple_scheduler.start()
    logger.info("调度器启动完成")
    
    logger.info(f"应用启动完成，监听 {settings.api_host}:{settings.api_port}")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭事件"""
    logger.info("应用关闭中...")
    # 停止调度器
    await simple_scheduler.stop()
    logger.info("应用关闭完成")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "阴阳师自动化调度系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}
