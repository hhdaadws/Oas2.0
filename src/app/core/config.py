"""
核心配置模块
"""
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """系统配置"""
    
    # 数据库
    database_url: str = Field(default="sqlite:///./data.db", env="DATABASE_URL")
    
    # OCR
    paddle_ocr_lang: str = Field(default="ch", env="PADDLE_OCR_LANG")
    
    # 模拟器
    mumu_manager_path: str = Field(default="", env="MUMU_MANAGER_PATH")
    adb_path: str = Field(default="adb", env="ADB_PATH")
    pkg_name: str = Field(default="com.netease.onmyoji", env="PKG_NAME")
    
    # 调度
    coop_times: str = Field(default="18:00,21:00", env="COOP_TIMES")
    stamina_threshold: int = Field(default=1000, env="STAMINA_THRESHOLD")
    delegate_time: str = Field(default="18:00", env="DELEGATE_TIME")
    
    # Web服务
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=9001, env="API_PORT")
    
    # 日志
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_path: str = Field(default="./logs", env="LOG_PATH")
    log_retention_days: int = Field(default=3, env="LOG_RETENTION_DAYS")
    
    # 备份
    backup_interval_days: int = Field(default=3, env="BACKUP_INTERVAL_DAYS")
    backup_retention_count: int = Field(default=3, env="BACKUP_RETENTION_COUNT")
    
    # 区服配置（固定）
    zones: List[str] = ["樱之华", "春之樱", "两情相悦", "枫之舞"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def coop_time_list(self) -> List[str]:
        """获取勾协时间列表"""
        return [t.strip() for t in self.coop_times.split(",")]


# 全局配置实例
settings = Settings()