"""
模拟器管理API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ....db.base import get_db
from ....db.models import Emulator
from ....core.logger import logger


router = APIRouter(prefix="/api/emulators", tags=["emulators"])


class EmulatorCreate(BaseModel):
    """创建模拟器"""
    name: str
    role: str  # coop|general|init|scan
    adb_addr: str
    instance_id: int


class EmulatorUpdate(BaseModel):
    """更新模拟器"""
    name: Optional[str] = None
    role: Optional[str] = None
    adb_addr: Optional[str] = None
    instance_id: Optional[int] = None
    state: Optional[str] = None


@router.get("/")
async def get_emulators(db: Session = Depends(get_db)):
    """
    获取模拟器列表
    """
    emulators = db.query(Emulator).all()
    
    result = []
    for emu in emulators:
        result.append({
            "id": emu.id,
            "name": emu.name,
            "role": emu.role,
            "adb_addr": emu.adb_addr,
            "instance_id": getattr(emu, 'instance_id', 0),
            "state": emu.state,
            "created_at": emu.created_at.isoformat(),
            "updated_at": emu.updated_at.isoformat()
        })
    
    return result


@router.post("/")
async def create_emulator(
    emulator: EmulatorCreate,
    db: Session = Depends(get_db)
):
    """
    创建模拟器
    """
    # 检查名称是否已存在
    existing = db.query(Emulator).filter(Emulator.name == emulator.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="模拟器名称已存在"
        )
    
    # 创建模拟器
    db_emulator = Emulator(
        name=emulator.name,
        role=emulator.role,
        adb_addr=emulator.adb_addr,
        state="disconnected"
    )
    
    # 设置instance_id（如果列存在）
    if hasattr(db_emulator, 'instance_id'):
        db_emulator.instance_id = emulator.instance_id
    
    db.add(db_emulator)
    db.commit()
    
    logger.info(f"创建模拟器: {emulator.name}")
    
    return {"message": "模拟器创建成功", "id": db_emulator.id}


@router.put("/{emulator_id}")
async def update_emulator(
    emulator_id: int,
    update: EmulatorUpdate,
    db: Session = Depends(get_db)
):
    """
    更新模拟器
    """
    emulator = db.query(Emulator).filter(Emulator.id == emulator_id).first()
    if not emulator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟器不存在"
        )
    
    # 更新字段
    if update.name is not None:
        emulator.name = update.name
    if update.role is not None:
        emulator.role = update.role
    if update.adb_addr is not None:
        emulator.adb_addr = update.adb_addr
    if update.instance_id is not None:
        emulator.instance_id = update.instance_id
    if update.state is not None:
        emulator.state = update.state
    
    db.commit()
    
    logger.info(f"更新模拟器: {emulator.name}")
    
    return {"message": "模拟器更新成功"}


@router.delete("/{emulator_id}")
async def delete_emulator(
    emulator_id: int,
    db: Session = Depends(get_db)
):
    """
    删除模拟器
    """
    emulator = db.query(Emulator).filter(Emulator.id == emulator_id).first()
    if not emulator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟器不存在"
        )
    
    db.delete(emulator)
    db.commit()
    
    logger.info(f"删除模拟器: {emulator.name}")
    
    return {"message": "模拟器删除成功"}
