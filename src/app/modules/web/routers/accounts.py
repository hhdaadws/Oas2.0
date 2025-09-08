"""
账号管理API
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta, time
import random

from ....db.base import get_db
from sqlalchemy import or_
from ....db.models import (
    Email,
    GameAccount,
    AccountRestConfig,
    RestPlan,
    Task,
    TaskRun,
    CoopPool,
    Log,
)
from ....core.constants import DEFAULT_TASK_CONFIG, AccountStatus
from ....core.logger import logger
from ...tasks import scheduler


router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# Pydantic模型
class EmailAccountCreate(BaseModel):
    """创建邮箱账号"""
    email: str
    password: str


class GameAccountCreate(BaseModel):
    """创建游戏账号"""
    login_id: str
    zone: str
    level: int = 1
    stamina: int = 0


class AccountUpdate(BaseModel):
    """更新账号信息"""
    status: Optional[int] = None
    progress: Optional[str] = None
    level: Optional[int] = None
    stamina: Optional[int] = None


class TaskConfigUpdate(BaseModel):
    """更新任务配置"""
    寄养: Optional[Dict[str, Any]] = None  # {enabled: bool, next_time: "2020-01-01 00:00"}
    委托: Optional[Dict[str, Any]] = None  # {enabled: bool, next_time: "2020-01-01 00:00"}
    勾协: Optional[Dict[str, Any]] = None  # {enabled: bool, next_time: "2020-01-01 00:00"}
    探索突破: Optional[Dict[str, Any]] = None  # {enabled: bool, stamina_threshold: int}
    结界卡合成: Optional[Dict[str, Any]] = None  # {enabled: bool, explore_count: int}
    加好友: Optional[Dict[str, Any]] = None  # {enabled: bool, next_time: "2020-01-01 00:00"}


class RestConfigUpdate(BaseModel):
    """更新休息配置"""
    mode: str = "random"  # random|custom
    start_time: Optional[str] = None  # HH:MM
    duration: Optional[int] = 2  # 小时数


@router.get("")
async def get_accounts(db: Session = Depends(get_db)):
    """
    获取账号列表（支持树形结构）
    """
    # 查询所有邮箱账号
    emails = db.query(Email).all()
    
    result = []
    for email in emails:
        email_data = {
            "type": "email",
            "email": email.email,
            "created_at": email.created_at.isoformat(),
            "children": []
        }
        
        # 查询该邮箱下的游戏账号
        game_accounts = db.query(GameAccount).filter(
            GameAccount.email_fk == email.email
        ).all()
        
        for account in game_accounts:
            email_data["children"].append({
                "type": "game",
                "id": account.id,
                "login_id": account.login_id,
                "zone": account.zone,
                "level": account.level,
                "stamina": account.stamina,
                "status": account.status,
                "progress": account.progress,
                "current_task": account.current_task,
                "task_config": account.task_config or DEFAULT_TASK_CONFIG
            })
        
        result.append(email_data)
    
    # 查询独立的游戏账号（无邮箱）
    independent_accounts = db.query(GameAccount).filter(
        GameAccount.email_fk == None
    ).all()
    
    for account in independent_accounts:
        result.append({
            "type": "game",
            "id": account.id,
            "login_id": account.login_id,
            "zone": account.zone,
            "level": account.level,
            "stamina": account.stamina,
            "status": account.status,
            "progress": account.progress,
            "current_task": account.current_task,
            "task_config": account.task_config or DEFAULT_TASK_CONFIG
        })
    
    return result


@router.post("/email")
async def create_email_account(
    account: EmailAccountCreate,
    db: Session = Depends(get_db)
):
    """
    添加邮箱账号
    """
    # 检查邮箱是否已存在
    existing = db.query(Email).filter(Email.email == account.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱账号已存在"
        )
    
    # 创建邮箱账号
    email_account = Email(
        email=account.email,
        password=account.password
    )
    db.add(email_account)
    db.commit()
    
    # 创建起号任务
    await scheduler.create_init_task(account.email)
    
    logger.info(f"创建邮箱账号: {account.email}")
    
    return {"message": "邮箱账号创建成功", "email": account.email}


@router.post("/game")
async def create_game_account(
    account: GameAccountCreate,
    db: Session = Depends(get_db)
):
    """
    添加ID账号（独立游戏账号）
    """
    # 检查login_id是否已存在
    existing = db.query(GameAccount).filter(
        GameAccount.login_id == account.login_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="游戏账号已存在"
        )
    
    # 创建游戏账号
    game_account = GameAccount(
        login_id=account.login_id,
        zone=account.zone,
        level=account.level,
        stamina=account.stamina,
        progress="ok",  # ID账号默认已完成初始化
        status=AccountStatus.ACTIVE,
        task_config=DEFAULT_TASK_CONFIG
    )
    db.add(game_account)
    db.commit()
    db.refresh(game_account)
    
    logger.info(f"创建游戏账号: {account.login_id}")
    
    return {
        "message": "游戏账号创建成功",
        "account": {
            "id": game_account.id,
            "login_id": game_account.login_id,
            "zone": game_account.zone
        }
    }


@router.put("/{account_id}")
async def update_account(
    account_id: int,
    update: AccountUpdate,
    db: Session = Depends(get_db)
):
    """
    更新账号状态和资源
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在"
        )
    
    # 更新字段
    if update.status is not None:
        account.status = update.status
    if update.progress is not None:
        account.progress = update.progress
    if update.level is not None:
        account.level = update.level
    if update.stamina is not None:
        old_stamina = account.stamina
        account.stamina = update.stamina
        
        # 检查是否触发条件任务
        from ....core.config import settings
        if old_stamina < settings.stamina_threshold <= update.stamina:
            # 触发探索/突破任务检查
            logger.info(f"账号 {account.login_id} 体力达到阈值，触发任务检查")
            # 这里调度器会在下一个检查周期自动处理
    
    
    account.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"更新账号 {account.login_id} 信息")
    
    return {"message": "账号更新成功"}


@router.put("/{account_id}/task-config")
async def update_task_config(
    account_id: int,
    config: TaskConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    更新任务配置
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在"
        )
    
    # 获取现有配置，如果为空则使用新的默认配置
    current_config = account.task_config or {}
    
    # 使用新的默认配置结构
    new_config = DEFAULT_TASK_CONFIG.copy()
    
    # 更新配置
    update_dict = config.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            new_config[key] = value
    
    account.task_config = new_config
    account.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"更新账号 {account.login_id} 任务配置")
    
    return {"message": "任务配置更新成功", "config": new_config}


@router.put("/{account_id}/rest-config")
async def update_rest_config(
    account_id: int,
    config: RestConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    更新休息配置
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在"
        )
    
    # 查询或创建休息配置
    rest_config = db.query(AccountRestConfig).filter(
        AccountRestConfig.account_id == account_id
    ).first()
    
    if not rest_config:
        rest_config = AccountRestConfig(account_id=account_id)
        db.add(rest_config)
    
    # 更新配置
    rest_config.mode = config.mode
    if config.mode == "custom":
        rest_config.rest_start = config.start_time
        rest_config.rest_duration = config.duration
    rest_config.updated_at = datetime.utcnow()
    
    db.commit()
    
    # 随机模式：若今日无计划则立即生成（7:00-23:00 内，2-3小时）
    if rest_config.mode == "random":
        today = datetime.now().date().isoformat()
        exists = db.query(RestPlan).filter(
            RestPlan.account_id == account_id,
            RestPlan.date == today
        ).first()
        if not exists:
            duration_hours = random.uniform(2, 3)
            base_date = datetime.now().date()
            start_min_dt = datetime.combine(base_date, time(7, 0))
            latest_start_dt = datetime.combine(base_date, time(23, 0)) - timedelta(hours=duration_hours)
            if latest_start_dt < start_min_dt:
                latest_start_dt = start_min_dt
            total_minutes = max(int((latest_start_dt - start_min_dt).total_seconds() // 60), 0)
            offset_min = random.randint(0, total_minutes)
            start_dt = start_min_dt + timedelta(minutes=offset_min)
            start_time = start_dt.strftime("%H:%M")

            end_dt = start_dt + timedelta(hours=duration_hours)
            end_limit_dt = datetime.combine(base_date, time(23, 0))
            if end_dt > end_limit_dt:
                end_dt = end_limit_dt
            end_time = end_dt.strftime("%H:%M")

            new_plan = RestPlan(
                account_id=account_id,
                date=today,
                start_time=start_time,
                end_time=end_time
            )
            db.add(new_plan)
            db.commit()
    
    logger.info(f"更新账号 {account.login_id} 休息配置")
    
    return {"message": "休息配置更新成功"}


@router.get("/{account_id}/rest-plan")
async def get_rest_plan(
    account_id: int,
    db: Session = Depends(get_db)
):
    """
    获取今日休息计划
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在"
        )
    
    today = datetime.now().date().isoformat()
    plan = db.query(RestPlan).filter(
        RestPlan.account_id == account_id,
        RestPlan.date == today
    ).first()
    
    if not plan:
        # 若无今日计划且模式为随机，则即时生成一个
        rest_config = db.query(AccountRestConfig).filter(
            AccountRestConfig.account_id == account_id
        ).first()
        if rest_config and rest_config.mode == "random":
            duration_hours = random.uniform(2, 3)
            base_date = datetime.now().date()
            start_min_dt = datetime.combine(base_date, time(7, 0))
            latest_start_dt = datetime.combine(base_date, time(23, 0)) - timedelta(hours=duration_hours)
            if latest_start_dt < start_min_dt:
                latest_start_dt = start_min_dt
            total_minutes = max(int((latest_start_dt - start_min_dt).total_seconds() // 60), 0)
            offset_min = random.randint(0, total_minutes)
            start_dt = start_min_dt + timedelta(minutes=offset_min)
            start_time = start_dt.strftime("%H:%M")

            end_dt = start_dt + timedelta(hours=duration_hours)
            end_limit_dt = datetime.combine(base_date, time(23, 0))
            if end_dt > end_limit_dt:
                end_dt = end_limit_dt
            end_time = end_dt.strftime("%H:%M")

            plan = RestPlan(
                account_id=account_id,
                date=today,
                start_time=start_time,
                end_time=end_time
            )
            db.add(plan)
            db.commit()
        else:
            return {"message": "今日暂无休息计划"}
    
    return {
        "date": plan.date,
        "start_time": plan.start_time,
        "end_time": plan.end_time
    }


@router.post("/init-status")
async def update_init_status(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    执行器更新起号状态（内部API）
    """
    account_id = data.get("account_id")
    status = data.get("status")
    zone = data.get("zone")
    level = data.get("level", 1)
    message = data.get("message", "")
    
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在"
        )
    
    # 更新账号状态
    account.status = status
    if status == AccountStatus.ACTIVE:
        account.progress = "ok"
    else:
        account.progress = "init"
    
    if zone:
        account.zone = zone
    if level:
        account.level = level
    
    account.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"更新起号状态: 账号={account.login_id}, 状态={status}, 消息={message}")
    
    return {"success": True, "account": {"id": account.id, "status": account.status}}


def _delete_account_by_id(db: Session, account_id: int) -> None:
    """Delete a game account and all related records."""
    # Delete task runs via task ids
    task_ids = [tid for (tid,) in db.query(Task.id).filter(Task.account_id == account_id).all()]
    if task_ids:
        db.query(TaskRun).filter(TaskRun.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
    # Delete tasks
    db.query(Task).filter(Task.account_id == account_id).delete(synchronize_session=False)
    # Delete rest config
    db.query(AccountRestConfig).filter(AccountRestConfig.account_id == account_id).delete(
        synchronize_session=False
    )
    # Delete rest plans
    db.query(RestPlan).filter(RestPlan.account_id == account_id).delete(synchronize_session=False)
    # Delete coop pool entries (as owner)
    try:
        db.query(CoopPool).filter(CoopPool.owner_account_id == account_id).delete(
            synchronize_session=False
        )
    except Exception:
        # 兼容旧结构（迁移前环境）
        db.query(CoopPool).filter(
            or_(getattr(CoopPool, 'account_id', None) == account_id,
                getattr(CoopPool, 'linked_account_id', None) == account_id)
        ).delete(synchronize_session=False)
    # Delete logs
    db.query(Log).filter(Log.account_id == account_id).delete(synchronize_session=False)
    # Finally delete the account itself if exists
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if account:
        db.delete(account)
    # No commit here; caller commits


@router.delete("/{account_id}")
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    """
    删除单个游戏账号（ID账号）及其关联数据
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在",
        )

    login_id = account.login_id
    _delete_account_by_id(db, account_id)
    db.commit()

    logger.info(f"删除游戏账号: {login_id}")
    return {"message": "账号删除成功"}


class BatchDeleteRequest(BaseModel):
    """批量删除请求体"""
    ids: List[int]


@router.post("/batch-delete")
async def batch_delete_accounts(req: BatchDeleteRequest, db: Session = Depends(get_db)):
    """
    批量删除多个游戏账号及其关联数据
    """
    ids = list(dict.fromkeys(req.ids or []))  # 去重保持顺序
    if not ids:
        return {"message": "未提供账号ID", "deleted": 0}

    deleted = 0
    for account_id in ids:
        account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
        if not account:
            continue
        login_id = account.login_id
        _delete_account_by_id(db, account_id)
        deleted += 1
        logger.info(f"批量删除账号: {login_id}")

    db.commit()
    return {"message": "批量删除完成", "deleted": deleted}


@router.delete("/email/{email}")
async def delete_email_account(email: str, db: Session = Depends(get_db)):
    """
    删除邮箱账号及其名下所有游戏账号和关联数据
    """
    email_obj = db.query(Email).filter(Email.email == email).first()
    if not email_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="邮箱账号不存在",
        )

    # Delete all linked game accounts
    accounts = db.query(GameAccount).filter(GameAccount.email_fk == email).all()
    for ga in accounts:
        _delete_account_by_id(db, ga.id)

    # Delete the email account itself
    db.delete(email_obj)
    db.commit()

    logger.info(f"删除邮箱账号及其关联账号: {email}")
    return {"message": "邮箱账号删除成功"}
