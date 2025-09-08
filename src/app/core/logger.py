"""
日志配置模块
"""
import sys
from pathlib import Path
from loguru import logger
from .config import settings


def setup_logger():
    """配置日志系统"""
    # 移除默认处理器
    logger.remove()
    
    # 创建日志目录
    log_dir = Path(settings.log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 控制台输出
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    )
    
    # 文件输出 - 全局日志
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="00:00",  # 每天午夜轮转
        retention=f"{settings.log_retention_days} days",
        encoding="utf-8",
        serialize=True  # JSON格式
    )
    
    # 错误日志单独记录
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="00:00",
        retention=f"{settings.log_retention_days * 2} days",
        encoding="utf-8"
    )
    
    return logger


def get_account_logger(account_id: str):
    """获取账号专用日志器"""
    log_dir = Path(settings.log_path) / "accounts"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    account_logger = logger.bind(account_id=account_id)
    account_logger.add(
        log_dir / f"account_{account_id}_{{time:YYYY-MM-DD}}.log",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="00:00",
        retention=f"{settings.log_retention_days} days",
        encoding="utf-8",
        filter=lambda record: record["extra"].get("account_id") == account_id
    )
    
    return account_logger


# 初始化日志系统
logger = setup_logger()