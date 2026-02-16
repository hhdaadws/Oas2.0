"""
Main application entrypoint
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .core.logger import logger
from .core.config import settings, BASE_DIR
from .db import init_db
from .modules.web import register_routers
from .modules.executor.service import executor_service
from .modules.tasks.feeder import feeder


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件"""

    EXEMPT_PATHS = {
        "/",
        "/health",
        "/api/auth/login",
        "/api/auth/status",
    }

    async def dispatch(self, request, call_next):
        path = request.url.path

        # 跳过不需要认证的路径
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # 跳过非 API 路径
        if not path.startswith("/api/"):
            return await call_next(request)

        # OPTIONS 请求不需要认证（CORS 预检）
        if request.method == "OPTIONS":
            return await call_next(request)

        # 检查 Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "未提供认证令牌"},
            )

        token = auth_header[7:]

        from .modules.web.routers.auth import verify_jwt_token
        if not verify_jwt_token(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "认证令牌无效或已过期"},
            )

        return await call_next(request)


app = FastAPI(
    title="YYS Automation",
    description="Multi-account task scheduler",
    version="1.0.0",
    debug=True,
)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    logger.info("starting app ...")
    init_db()
    register_routers(app)
    _mount_frontend(app)
    logger.info(f"app started at {settings.api_host}:{settings.api_port}")


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("shutting down ...")
    await feeder.stop()
    await executor_service.stop()
    logger.info("shutdown complete")


# 前端 index.html 路径（由 _mount_frontend 设置）
_frontend_index = None


@app.get("/")
async def root():
    if _frontend_index and Path(_frontend_index).is_file():
        return FileResponse(_frontend_index)
    return {"message": "YYS Automation API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


def _mount_frontend(application: FastAPI):
    """挂载前端 build 产物为静态文件，支持 SPA 路由。"""
    # 打包模式: exe 旁边的 frontend_dist/
    # 开发模式: 项目根下 frontend/dist/（npm run build 后）
    candidates = [
        BASE_DIR / "frontend_dist",
        BASE_DIR / "frontend" / "dist",
    ]

    frontend_dir = None
    for d in candidates:
        if d.is_dir() and (d / "index.html").exists():
            frontend_dir = d
            break

    if frontend_dir is None:
        logger.warning("前端静态文件未找到，跳过挂载（开发模式请用 Vite dev server）")
        return

    logger.info(f"挂载前端静态文件: {frontend_dir}")

    # 设置全局变量，让 root() 路由也返回 index.html
    global _frontend_index
    _frontend_index = str(frontend_dir / "index.html")

    # 挂载 Vite build 产物的 assets 子目录（JS/CSS）
    assets_dir = frontend_dir / "assets"
    if assets_dir.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="frontend-assets",
        )

    # SPA fallback：所有非 /api 路径返回 index.html
    @application.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = frontend_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
