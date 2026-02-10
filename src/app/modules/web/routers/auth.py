"""
认证 API
"""
import time
import pyotp
import jwt
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ....core.config import TOTP_SECRET, JWT_SECRET, JWT_EXPIRE_HOURS
from ....core.logger import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """TOTP 登录请求"""
    code: str


class LoginResponse(BaseModel):
    """登录响应"""
    token: str
    expires_in: int


def _create_jwt_token() -> tuple:
    """创建 JWT token"""
    expire_seconds = JWT_EXPIRE_HOURS * 3600
    payload = {
        "authenticated": True,
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
    """验证 TOTP 验证码并返回 JWT"""
    totp = pyotp.TOTP(TOTP_SECRET)
    if not totp.verify(req.code, valid_window=2):
        logger.warning("登录失败 - 验证码无效")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码无效或已过期",
        )
    token, expires_in = _create_jwt_token()
    logger.info("用户登录成功")
    return LoginResponse(token=token, expires_in=expires_in)


@router.get("/status")
async def auth_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """检查认证状态"""
    if not credentials or not verify_jwt_token(credentials.credentials):
        return {"authenticated": False}
    return {"authenticated": True}
