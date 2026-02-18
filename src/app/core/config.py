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
    if getattr(sys, "frozen", False):
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
    # 识图帧缓存总开关
    vision_frame_cache_enabled: bool = Field(
        default=True, env="VISION_FRAME_CACHE_ENABLED"
    )
    # 同帧识图结果缓存有效期（毫秒）
    # 默认 5000ms，覆盖 ensure_game_ready 的 2s 轮询与处理耗时。
    vision_frame_cache_ttl_ms: int = Field(
        default=5000, env="VISION_FRAME_CACHE_TTL_MS"
    )
    # 同帧近似判定阈值（缩略量化图的平均差值）
    # 值越大越宽松，命中率更高，但需防止 UI 变化被误判为同帧。
    vision_frame_similarity_threshold: float = Field(
        default=0.8, env="VISION_FRAME_SIMILARITY_THRESHOLD"
    )
    # 是否开启跨模拟器共享识图缓存（仅共享同帧识别结果）
    vision_cross_emulator_cache_enabled: bool = Field(
        default=False, env="VISION_CROSS_EMULATOR_CACHE_ENABLED"
    )
    # 跨模拟器共享缓存每个桶的最大保留条数（LRU）
    vision_cross_emulator_shared_bucket_size: int = Field(
        default=8, env="VISION_CROSS_EMULATOR_SHARED_BUCKET_SIZE"
    )
    # 同帧连续 miss 最多跳过次数（到达后强制重检）
    vision_unchanged_skip_max: int = Field(default=2, env="VISION_UNCHANGED_SKIP_MAX")
    # 弹窗关闭后立即重试的最小 sleep（毫秒）
    vision_min_retry_sleep_ms: int = Field(default=50, env="VISION_MIN_RETRY_SLEEP_MS")
    # 识图缓存统计日志输出间隔（秒）
    vision_cache_stats_interval_sec: int = Field(
        default=10, env="VISION_CACHE_STATS_INTERVAL_SEC"
    )

    # 调度
    coop_times: str = Field(default="18:00,21:00", env="COOP_TIMES")
    stamina_threshold: int = Field(default=1000, env="STAMINA_THRESHOLD")

    # Web服务
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=9001, env="API_PORT")
    run_mode: str = Field(default="local", env="RUN_MODE")
    cloud_api_base_url: str = Field(default="", env="CLOUD_API_BASE_URL")
    cloud_agent_node_id: str = Field(default="local-node", env="CLOUD_AGENT_NODE_ID")
    cloud_manager_username: str = Field(default="", env="CLOUD_MANAGER_USERNAME")
    cloud_manager_password: str = Field(default="", env="CLOUD_MANAGER_PASSWORD")
    cloud_poll_interval_sec: int = Field(default=5, env="CLOUD_POLL_INTERVAL_SEC")
    cloud_lease_sec: int = Field(default=90, env="CLOUD_LEASE_SEC")
    cloud_timeout_sec: int = Field(default=15, env="CLOUD_TIMEOUT_SEC")

    # 日志
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_path: str = Field(default=str(BASE_DIR / "logs"), env="LOG_PATH")
    log_retention_days: int = Field(default=3, env="LOG_RETENTION_DAYS")
    log_console_enabled: bool = Field(default=True, env="LOG_CONSOLE_ENABLED")
    log_enqueue_enabled: bool = Field(default=True, env="LOG_ENQUEUE_ENABLED")
    log_file_format: str = Field(default="text", env="LOG_FILE_FORMAT")
    log_access_enabled: bool = Field(default=True, env="LOG_ACCESS_ENABLED")
    log_access_path: str = Field(default="", env="LOG_ACCESS_PATH")
    log_rotation: str = Field(default="00:00", env="LOG_ROTATION")

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
