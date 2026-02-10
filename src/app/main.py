"""
Main application entrypoint
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .core.logger import logger
from .core.config import settings
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
