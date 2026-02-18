"""
认证 API
"""
import time
import pyotp
import jwt
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from ....core.config import TOTP_SECRET, JWT_SECRET, JWT_EXPIRE_HOURS
from ....core.logger import logger
from ...cloud import cloud_task_poller, runtime_mode_state, CloudApiError

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """登录请求（本地验证码 / 云端管理员密码）"""
    mode: str = Field(default="local")
    code: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="")


class LoginResponse(BaseModel):
    """登录响应"""
    token: str
    expires_in: int
    mode: str


def _create_jwt_token(mode: str) -> tuple:
    """创建 JWT token"""
    expire_seconds = JWT_EXPIRE_HOURS * 3600
    payload = {
        "authenticated": True,
        "mode": mode,
        "iat": int(time.time()),
        "exp": int(time.time()) + expire_seconds,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token, expire_seconds


def verify_jwt_token(token: str) -> bool:
    """验证 JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("authenticated", False)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """登录并返回 JWT。"""
    mode = (req.mode or "local").strip().lower()
    if mode == "cloud":
        username = (req.username or "").strip()
        password = req.password or ""
        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="云端模式需要管理员账号和密码",
            )
        try:
            await cloud_task_poller.verify_manager_login(
                username=username, password=password
            )
        except CloudApiError as exc:
            logger.warning(f"云端登录失败: {exc}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"云端登录失败: {exc}",
            )
        runtime_mode_state.set_manager_credentials(username=username, password=password)
        runtime_mode_state.set_mode("cloud")
        token, expires_in = _create_jwt_token(mode="cloud")
        logger.info(f"云端模式登录成功: {username}")
        return LoginResponse(token=token, expires_in=expires_in, mode="cloud")

    if mode != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode 仅支持 local 或 cloud",
        )

    totp = pyotp.TOTP(TOTP_SECRET)
    if not totp.verify(req.code, valid_window=2):
        logger.warning("登录失败 - 验证码无效")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码无效或已过期",
        )

    runtime_mode_state.set_mode("local")
    token, expires_in = _create_jwt_token(mode="local")
    logger.info("本地模式登录成功")
    return LoginResponse(token=token, expires_in=expires_in, mode="local")


@router.get("/status")
async def auth_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """检查认证状态"""
    if not credentials or not verify_jwt_token(credentials.credentials):
        return {"authenticated": False, "mode": runtime_mode_state.get_mode()}
    return {"authenticated": True, "mode": runtime_mode_state.get_mode()}
