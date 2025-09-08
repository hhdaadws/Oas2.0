"""
系统配置API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ....db.base import get_db
from ....core.config import settings
from ....core.logger import logger


router = APIRouter(prefix="/api/config", tags=["config"])


class SystemConfig(BaseModel):
    """系统配置"""
    # ADB配置
    adb_path: str = "adb"
    app_start_method: str = "monkey"  # monkey|am_start|intent
    app_package: str = "com.netease.onmyoji"
    app_activity: str = "com.netease.onmyoji.Onmyoji"
    
    # 截图配置
    capture_method: str = "adb"  # adb|ipc
    capture_quality: int = 80
    capture_timeout: int = 10
    
    # 识别配置  
    template_threshold: float = 0.8
    ocr_language: str = "ch"
    
    # 任务配置
    task_timeout: int = 300
    task_retry_count: int = 3
    
    # 调度配置
    global_rest_start: str = "00:00"
    global_rest_end: str = "06:00"
    stamina_threshold: int = 1000


# 全局配置实例
_system_config = SystemConfig()


@router.get("/")
async def get_system_config():
    """
    获取系统配置
    """
    return {
        "adb": {
            "path": _system_config.adb_path,
            "start_method": _system_config.app_start_method,
            "package": _system_config.app_package,
            "activity": _system_config.app_activity
        },
        "capture": {
            "method": _system_config.capture_method,
            "quality": _system_config.capture_quality,
            "timeout": _system_config.capture_timeout
        },
        "recognition": {
            "template_threshold": _system_config.template_threshold,
            "ocr_language": _system_config.ocr_language
        },
        "task": {
            "timeout": _system_config.task_timeout,
            "retry_count": _system_config.task_retry_count
        },
        "schedule": {
            "global_rest_start": _system_config.global_rest_start,
            "global_rest_end": _system_config.global_rest_end,
            "stamina_threshold": _system_config.stamina_threshold
        }
    }


@router.put("/")
async def update_system_config(config: Dict[str, Any]):
    """
    更新系统配置
    """
    global _system_config
    
    try:
        # 更新ADB配置
        if "adb" in config:
            adb_config = config["adb"]
            if "path" in adb_config:
                _system_config.adb_path = adb_config["path"]
            if "start_method" in adb_config:
                _system_config.app_start_method = adb_config["start_method"]
            if "package" in adb_config:
                _system_config.app_package = adb_config["package"]
            if "activity" in adb_config:
                _system_config.app_activity = adb_config["activity"]
        
        # 更新截图配置
        if "capture" in config:
            capture_config = config["capture"]
            if "method" in capture_config:
                _system_config.capture_method = capture_config["method"]
            if "quality" in capture_config:
                _system_config.capture_quality = capture_config["quality"]
            if "timeout" in capture_config:
                _system_config.capture_timeout = capture_config["timeout"]
        
        # 更新识别配置
        if "recognition" in config:
            recognition_config = config["recognition"]
            if "template_threshold" in recognition_config:
                _system_config.template_threshold = recognition_config["template_threshold"]
            if "ocr_language" in recognition_config:
                _system_config.ocr_language = recognition_config["ocr_language"]
        
        # 更新任务配置
        if "task" in config:
            task_config = config["task"]
            if "timeout" in task_config:
                _system_config.task_timeout = task_config["timeout"]
            if "retry_count" in task_config:
                _system_config.task_retry_count = task_config["retry_count"]
        
        # 更新调度配置
        if "schedule" in config:
            schedule_config = config["schedule"]
            if "global_rest_start" in schedule_config:
                _system_config.global_rest_start = schedule_config["global_rest_start"]
            if "global_rest_end" in schedule_config:
                _system_config.global_rest_end = schedule_config["global_rest_end"]
            if "stamina_threshold" in schedule_config:
                _system_config.stamina_threshold = schedule_config["stamina_threshold"]
        
        logger.info("系统配置更新成功")
        
        return {"message": "配置更新成功"}
        
    except Exception as e:
        logger.error(f"更新系统配置失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"配置更新失败: {str(e)}")


def get_current_config() -> SystemConfig:
    """获取当前配置实例"""
    return _system_config