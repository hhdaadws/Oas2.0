"""
账号管理API
"""
from typing import List, Optional, Dict, Any
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
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
from ...lineup import LINEUP_SUPPORTED_TASKS, merge_lineup_with_defaults


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
    gouyu: Optional[int] = None
    lanpiao: Optional[int] = None
    gold: Optional[int] = None
    remark: Optional[str] = None


class TaskConfigUpdate(BaseModel):
    """更新任务配置"""

    model_config = ConfigDict(
        populate_by_name=True, validate_by_alias=True, extra="ignore"
    )

    foster: Optional[Dict[str, Any]] = Field(default=None, alias="寄养")
    delegate: Optional[Dict[str, Any]] = Field(default=None, alias="委托")
    delegate_help: Optional[Dict[str, Any]] = Field(default=None, alias="弥助")
    coop: Optional[Dict[str, Any]] = Field(default=None, alias="勾协")
    explore: Optional[Dict[str, Any]] = Field(default=None, alias="探索突破")
    card_synthesis: Optional[Dict[str, Any]] = Field(default=None, alias="结界卡合成")
    add_friend: Optional[Dict[str, Any]] = Field(default=None, alias="加好友")
    collect_login_gift: Optional[Dict[str, Any]] = Field(default=None, alias="领取登录礼包")
    collect_mail: Optional[Dict[str, Any]] = Field(default=None, alias="领取邮件")
    climb_tower: Optional[Dict[str, Any]] = Field(default=None, alias="爬塔")
    fengmo: Optional[Dict[str, Any]] = Field(default=None, alias="逢魔")
    digui: Optional[Dict[str, Any]] = Field(default=None, alias="地鬼")
    daoguan: Optional[Dict[str, Any]] = Field(default=None, alias="道馆")
    signin: Optional[Dict[str, Any]] = Field(
        default=None, alias="签到"
    )  # {enabled: bool, status: "已签到|未签到", signed_date: "YYYY-MM-DD"|null}


class RestConfigUpdate(BaseModel):
    """更新休息配置"""

    mode: str = "random"  # random|custom
    start_time: Optional[str] = None  # HH:MM
    duration: Optional[int] = 2  # 小时数


def _merge_task_config_with_defaults(task_config: Any) -> Dict[str, Any]:
    """按“默认 + 现有配置”规则规范化任务配置。"""
    merged_config = deepcopy(DEFAULT_TASK_CONFIG)

    if not isinstance(task_config, dict):
        return merged_config

    for key, value in task_config.items():
        if isinstance(value, dict):
            base_value = merged_config.get(key, {})
            if not isinstance(base_value, dict):
                base_value = {}
            base_value.update(value)
            merged_config[key] = base_value
        else:
            merged_config[key] = value

    return merged_config


@router.get("")
async def get_accounts(db: Session = Depends(get_db)):
    """
    获取账号列表（支持树形结构）
    """
    # 查询所有邮箱账号
    emails = db.query(Email).all()

    result = []
    need_commit = False

    for email in emails:
        email_data = {
            "type": "email",
            "email": email.email,
            "created_at": email.created_at.isoformat(),
            "children": [],
        }

        # 查询该邮箱下的游戏账号
        game_accounts = (
            db.query(GameAccount).filter(GameAccount.email_fk == email.email).all()
        )

        for account in game_accounts:
            normalized_task_config = _merge_task_config_with_defaults(
                account.task_config
            )
            if account.task_config != normalized_task_config:
                account.task_config = normalized_task_config
                account.updated_at = datetime.utcnow()
                need_commit = True

            email_data["children"].append(
                {
                    "type": "game",
                    "id": account.id,
                    "login_id": account.login_id,
                    "zone": account.zone,
                    "level": account.level,
                    "stamina": account.stamina,
                    "gouyu": account.gouyu,
                    "lanpiao": account.lanpiao,
                    "gold": account.gold,
                    "status": account.status,
                    "progress": account.progress,
                    "current_task": account.current_task,
                    "task_config": normalized_task_config,
                    "lineup_config": account.lineup_config or {},
                    "remark": account.remark or "",
                }
            )

        result.append(email_data)

    # 查询独立的游戏账号（无邮箱）
    independent_accounts = (
        db.query(GameAccount).filter(GameAccount.email_fk == None).all()
    )

    for account in independent_accounts:
        normalized_task_config = _merge_task_config_with_defaults(account.task_config)
        if account.task_config != normalized_task_config:
            account.task_config = normalized_task_config
            account.updated_at = datetime.utcnow()
            need_commit = True

        result.append(
            {
                "type": "game",
                "id": account.id,
                "login_id": account.login_id,
                "zone": account.zone,
                "level": account.level,
                "stamina": account.stamina,
                "gouyu": account.gouyu,
                "lanpiao": account.lanpiao,
                "gold": account.gold,
                "status": account.status,
                "progress": account.progress,
                "current_task": account.current_task,
                "task_config": normalized_task_config,
                "lineup_config": account.lineup_config or {},
                "remark": account.remark or "",
            }
        )

    if need_commit:
        db.commit()

    return result


@router.post("/email")
async def create_email_account(
    account: EmailAccountCreate, db: Session = Depends(get_db)
):
    """
    添加邮箱账号
    """
    # 检查邮箱是否已存在
    existing = db.query(Email).filter(Email.email == account.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱账号已存在")

    # 创建邮箱账号
    email_account = Email(email=account.email, password=account.password)
    db.add(email_account)
    db.commit()

    # 创建起号任务
    await scheduler.create_init_task(account.email)

    logger.info(f"创建邮箱账号: {account.email}")

    return {"message": "邮箱账号创建成功", "email": account.email}


@router.post("/game")
async def create_game_account(
    account: GameAccountCreate, db: Session = Depends(get_db)
):
    """
    添加ID账号（独立游戏账号）
    """
    # 检查login_id是否已存在
    existing = (
        db.query(GameAccount).filter(GameAccount.login_id == account.login_id).first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="游戏账号已存在")

    # 创建游戏账号
    game_account = GameAccount(
        login_id=account.login_id,
        zone=account.zone,
        level=account.level,
        stamina=account.stamina,
        progress="ok",  # ID账号默认已完成初始化
        status=AccountStatus.ACTIVE,
        task_config=DEFAULT_TASK_CONFIG,
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
            "zone": game_account.zone,
        },
    }


@router.put("/{account_id}")
async def update_account(
    account_id: int, update: AccountUpdate, db: Session = Depends(get_db)
):
    """
    更新账号状态和资源
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

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

    if update.remark is not None:
        account.remark = update.remark
    if update.gouyu is not None:
        account.gouyu = update.gouyu
    if update.lanpiao is not None:
        account.lanpiao = update.lanpiao
    if update.gold is not None:
        account.gold = update.gold

    account.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"更新账号 {account.login_id} 信息")

    return {"message": "账号更新成功"}


@router.put("/{account_id}/task-config")
async def update_task_config(
    account_id: int, config: TaskConfigUpdate, db: Session = Depends(get_db)
):
    """
    更新任务配置
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    merged_config = _merge_task_config_with_defaults(account.task_config)

    # Pydantic v2 推荐 model_dump；只取显式传入字段
    update_dict = config.model_dump(exclude_unset=True, by_alias=True)

    # 若请求体未携带有效字段，直接保持现有配置，避免误重置
    if not update_dict:
        logger.warning(f"更新账号 {account.login_id} 任务配置：请求体为空，忽略本次更新")
        return {"message": "任务配置未变更", "config": merged_config}

    # 合并更新字段
    for key, value in update_dict.items():
        if value is None:
            continue
        if isinstance(value, dict):
            base_value = merged_config.get(key, {})
            if not isinstance(base_value, dict):
                base_value = {}
            base_value.update(value)
            merged_config[key] = base_value
        else:
            merged_config[key] = value

    account.task_config = merged_config
    account.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"更新账号 {account.login_id} 任务配置")

    return {"message": "任务配置更新成功", "config": merged_config}


@router.put("/{account_id}/rest-config")
async def update_rest_config(
    account_id: int, config: RestConfigUpdate, db: Session = Depends(get_db)
):
    """
    更新休息配置
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    # 查询或创建休息配置
    rest_config = (
        db.query(AccountRestConfig)
        .filter(AccountRestConfig.account_id == account_id)
        .first()
    )

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
        exists = (
            db.query(RestPlan)
            .filter(RestPlan.account_id == account_id, RestPlan.date == today)
            .first()
        )
        if not exists:
            duration_hours = random.uniform(2, 3)
            base_date = datetime.now().date()
            start_min_dt = datetime.combine(base_date, time(7, 0))
            latest_start_dt = datetime.combine(base_date, time(23, 0)) - timedelta(
                hours=duration_hours
            )
            if latest_start_dt < start_min_dt:
                latest_start_dt = start_min_dt
            total_minutes = max(
                int((latest_start_dt - start_min_dt).total_seconds() // 60), 0
            )
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
                end_time=end_time,
            )
            db.add(new_plan)
            db.commit()

    logger.info(f"更新账号 {account.login_id} 休息配置")

    return {"message": "休息配置更新成功"}


@router.get("/{account_id}/rest-plan")
async def get_rest_plan(account_id: int, db: Session = Depends(get_db)):
    """
    获取今日休息计划
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    today = datetime.now().date().isoformat()
    plan = (
        db.query(RestPlan)
        .filter(RestPlan.account_id == account_id, RestPlan.date == today)
        .first()
    )

    if not plan:
        # 若无今日计划且模式为随机，则即时生成一个
        rest_config = (
            db.query(AccountRestConfig)
            .filter(AccountRestConfig.account_id == account_id)
            .first()
        )
        if rest_config and rest_config.mode == "random":
            duration_hours = random.uniform(2, 3)
            base_date = datetime.now().date()
            start_min_dt = datetime.combine(base_date, time(7, 0))
            latest_start_dt = datetime.combine(base_date, time(23, 0)) - timedelta(
                hours=duration_hours
            )
            if latest_start_dt < start_min_dt:
                latest_start_dt = start_min_dt
            total_minutes = max(
                int((latest_start_dt - start_min_dt).total_seconds() // 60), 0
            )
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
                end_time=end_time,
            )
            db.add(plan)
            db.commit()
        else:
            return {"message": "今日暂无休息计划"}

    return {"date": plan.date, "start_time": plan.start_time, "end_time": plan.end_time}


@router.post("/init-status")
async def update_init_status(data: Dict[str, Any], db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

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
    task_ids = [
        tid for (tid,) in db.query(Task.id).filter(Task.account_id == account_id).all()
    ]
    if task_ids:
        db.query(TaskRun).filter(TaskRun.task_id.in_(task_ids)).delete(
            synchronize_session=False
        )
    # Delete tasks
    db.query(Task).filter(Task.account_id == account_id).delete(
        synchronize_session=False
    )
    # Delete rest config
    db.query(AccountRestConfig).filter(
        AccountRestConfig.account_id == account_id
    ).delete(synchronize_session=False)
    # Delete rest plans
    db.query(RestPlan).filter(RestPlan.account_id == account_id).delete(
        synchronize_session=False
    )
    # Delete coop pool entries (as owner)
    try:
        db.query(CoopPool).filter(CoopPool.owner_account_id == account_id).delete(
            synchronize_session=False
        )
    except Exception:
        # 兼容旧结构（迁移前环境）
        db.query(CoopPool).filter(
            or_(
                getattr(CoopPool, "account_id", None) == account_id,
                getattr(CoopPool, "linked_account_id", None) == account_id,
            )
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


# ───────── 阵容分组配置 ─────────


class LineupItemUpdate(BaseModel):
    group: int = Field(ge=1, le=7)
    position: int = Field(ge=1, le=7)


class LineupConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    逢魔: Optional[Dict[str, int]] = None
    地鬼: Optional[Dict[str, int]] = None
    探索: Optional[Dict[str, int]] = None
    结界突破: Optional[Dict[str, int]] = None
    道馆: Optional[Dict[str, int]] = None


@router.get("/{account_id}/lineup-config")
async def get_lineup_config(account_id: int, db: Session = Depends(get_db)):
    """获取账号阵容分组配置"""
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    merged = merge_lineup_with_defaults(account.lineup_config or {})
    return merged


@router.put("/{account_id}/lineup-config")
async def update_lineup_config(
    account_id: int, config: LineupConfigUpdate, db: Session = Depends(get_db)
):
    """更新账号阵容分组配置"""
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    current = account.lineup_config or {}
    update_dict = config.model_dump(exclude_unset=True)

    for key, value in update_dict.items():
        if value is not None and isinstance(value, dict):
            current[key] = value

    from sqlalchemy.orm.attributes import flag_modified

    account.lineup_config = current
    flag_modified(account, "lineup_config")
    account.updated_at = datetime.utcnow()
    db.commit()

    merged = merge_lineup_with_defaults(account.lineup_config)
    logger.info(f"更新账号 {account.login_id} 阵容配置")

    return {"message": "阵容配置更新成功", "config": merged}
