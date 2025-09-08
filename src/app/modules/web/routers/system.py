"""
系统配置 API
"""
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ....core.config import settings
from ....core.logger import logger
from ....db.base import get_db
from ....db.models import SystemConfig


router = APIRouter(prefix="/api/system", tags=["system"])


class SystemSettings(BaseModel):
    adb_path: str
    mumu_manager_path: str
    nemu_folder: str
    pkg_name: str
    launch_mode: str
    ipc_dll_path: str
    activity_name: str
    python_path: Optional[str] = None


class SystemSettingsUpdate(BaseModel):
    adb_path: Optional[str] = None
    mumu_manager_path: Optional[str] = None
    nemu_folder: Optional[str] = None
    pkg_name: Optional[str] = None
    launch_mode: Optional[str] = None  # adb|ipc|mumu
    ipc_dll_path: Optional[str] = None
    activity_name: Optional[str] = None
    python_path: Optional[str] = None


def _serialize_settings() -> Dict[str, str]:
    return {
        "adb_path": settings.adb_path,
        "mumu_manager_path": settings.mumu_manager_path,
        "nemu_folder": settings.nemu_folder,
        "pkg_name": settings.pkg_name,
        "launch_mode": settings.launch_mode,
        "ipc_dll_path": settings.ipc_dll_path,
        "activity_name": settings.activity_name,
        "python_path": None,
    }


@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)) -> SystemSettings:
    """获取系统配置：优先数据库，缺省回退到运行配置。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if row:
        return SystemSettings(
            adb_path=row.adb_path or settings.adb_path,
            mumu_manager_path=row.mumu_manager_path or settings.mumu_manager_path,
            nemu_folder=row.nemu_folder or settings.nemu_folder,
            pkg_name=row.pkg_name or settings.pkg_name,
            launch_mode=row.launch_mode or settings.launch_mode,
            ipc_dll_path=row.ipc_dll_path or settings.ipc_dll_path,
            activity_name=row.activity_name or settings.activity_name,
            python_path=row.python_path or None,
        )
    return SystemSettings(**_serialize_settings())


def _upsert_system_config(db: Session, data: Dict[str, str]) -> SystemConfig:
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    if not row:
        row = SystemConfig()
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.put("/settings")
async def update_settings(body: SystemSettingsUpdate, db: Session = Depends(get_db)):
    """更新系统配置（写入数据库）。"""
    apply: Dict[str, str] = {}
    if body.adb_path is not None:
        apply["adb_path"] = body.adb_path
    if body.mumu_manager_path is not None:
        apply["mumu_manager_path"] = body.mumu_manager_path
    if body.nemu_folder is not None:
        apply["nemu_folder"] = body.nemu_folder
    if body.pkg_name is not None:
        apply["pkg_name"] = body.pkg_name
    if body.launch_mode is not None:
        if body.launch_mode not in {"adb_monkey", "adb_intent", "am_start"}:
            raise HTTPException(status_code=400, detail="launch_mode 必须是 adb_monkey|adb_intent|am_start 之一")
        apply["launch_mode"] = body.launch_mode
    if body.ipc_dll_path is not None:
        apply["ipc_dll_path"] = body.ipc_dll_path
    if body.activity_name is not None:
        apply["activity_name"] = body.activity_name
    if body.python_path is not None:
        apply["python_path"] = body.python_path

    if not apply:
        return {"message": "未提供任何需要更新的配置"}

    row = _upsert_system_config(db, apply)
    logger.info("系统配置已更新到数据库")
    return {
        "message": "配置已保存",
        "settings": {
            "adb_path": row.adb_path,
            "mumu_manager_path": row.mumu_manager_path,
            "nemu_folder": row.nemu_folder,
            "pkg_name": row.pkg_name,
            "launch_mode": row.launch_mode,
            "ipc_dll_path": row.ipc_dll_path,
            "activity_name": row.activity_name,
            "python_path": row.python_path,
        },
    }
