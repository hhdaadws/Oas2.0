"""
核心配置模块
"""
import sys
import secrets as _secrets
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


def _get_base_dir() -> Path:
    """获取项目根目录，兼容开发模式和 PyInstaller 打包模式。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：exe 所在目录
        return Path(sys.executable).resolve().parent
    else:
        # 开发模式：config.py → core/ → app/ → src/ → 项目根
        return Path(__file__).resolve().parent.parent.parent.parent


BASE_DIR = _get_base_dir()

# TOTP 密钥（固定，仅开发者知晓）
TOTP_SECRET = "JBSWY3DPEHPK3PXP"

# JWT 过期时间（小时）
JWT_EXPIRE_HOURS = 24


class Settings(BaseSettings):
    """系统配置"""

    # 数据库
    database_url: str = Field(
        default=f"sqlite:///{(BASE_DIR / 'data.db').as_posix()}",
        env="DATABASE_URL",
    )

    # JWT 签名密钥（持久化，重启后 token 仍有效）
    jwt_secret: str = Field(default="", env="JWT_SECRET")
    
    # OCR
    paddle_ocr_lang: str = Field(default="ch", env="PADDLE_OCR_LANG")
    ocr_model_dir: str = Field(default=str(BASE_DIR / "ocr_model"), env="OCR_MODEL_DIR")
    
    # 模拟器/启动配置
    mumu_manager_path: str = Field(default="", env="MUMU_MANAGER_PATH")
    adb_path: str = Field(default="adb", env="ADB_PATH")
    pkg_name: str = Field(default="com.netease.onmyoji", env="PKG_NAME")
    # 阴阳师启动方式: adb|ipc|mumu
    launch_mode: str = Field(default="adb_monkey", env="LAUNCH_MODE")
    # IPC DLL 路径（可选）
    ipc_dll_path: str = Field(default="", env="IPC_DLL_PATH")
    # MuMu 安装目录，用于定位 IPC DLL
    nemu_folder: str = Field(default="", env="NEMU_FOLDER")
    # ADB intent 启动时的 Activity 名称
    activity_name: str = Field(default=".MainActivity", env="ACTIVITY_NAME")
    # 运行链路截图方式
    capture_method: str = Field(default="adb", env="CAPTURE_METHOD")
    
    # 调度
    coop_times: str = Field(default="18:00,21:00", env="COOP_TIMES")
    stamina_threshold: int = Field(default=1000, env="STAMINA_THRESHOLD")
    
    # Web服务
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=9001, env="API_PORT")
    
    # 日志
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_path: str = Field(default=str(BASE_DIR / "logs"), env="LOG_PATH")
    log_retention_days: int = Field(default=3, env="LOG_RETENTION_DAYS")
    
    # 备份
    backup_interval_days: int = Field(default=3, env="BACKUP_INTERVAL_DAYS")
    backup_retention_count: int = Field(default=3, env="BACKUP_RETENTION_COUNT")

    # 线程池（多模拟器并发优化，0 表示自动计算）
    io_thread_pool_size: int = Field(default=0, env="IO_THREAD_POOL_SIZE")
    compute_thread_pool_size: int = Field(default=0, env="COMPUTE_THREAD_POOL_SIZE")

    # OCR 实例池（支持并行推理）
    ocr_pool_size: int = Field(default=2, env="OCR_POOL_SIZE")
    digit_ocr_pool_size: int = Field(default=2, env="DIGIT_OCR_POOL_SIZE")
    
    class Config:
        env_file = str(BASE_DIR / ".env")
        case_sensitive = False
        extra = "ignore"
    
    @property
    def coop_time_list(self) -> list[str]:
        """获取勾协时间列表"""
        return [t.strip() for t in self.coop_times.split(",")]


# 全局配置实例
settings = Settings()


def _ensure_jwt_secret() -> str:
    """确保 JWT_SECRET 持久化：优先从 settings 读取，否则生成并写入 .env"""
    if settings.jwt_secret:
        return settings.jwt_secret
    generated = _secrets.token_hex(32)
    env_path = BASE_DIR / ".env"
    with open(env_path, "a", encoding="utf-8") as f:
        f.write(f"\nJWT_SECRET={generated}\n")
    return generated


JWT_SECRET = _ensure_jwt_secret()
