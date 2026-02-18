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
    GameAccount,
    AccountRestConfig,
    RestPlan,
    SystemConfig,
    Task,
    TaskRun,
    CoopPool,
    Log,
)
from ....core.constants import DEFAULT_TASK_CONFIG, DEFAULT_INIT_TASK_CONFIG, AccountStatus, build_default_task_config, build_default_explore_progress
from ....core.logger import logger
from ...lineup import LINEUP_SUPPORTED_TASKS, merge_lineup_with_defaults
from ...shikigami import merge_shikigami_with_defaults


router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# Pydantic模型
class GameAccountCreate(BaseModel):
    """创建游戏账号"""

    login_id: str
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
    gongxun: Optional[int] = None
    xunzhang: Optional[int] = None
    tupo_ticket: Optional[int] = None
    fanhe_level: Optional[int] = None
    jiuhu_level: Optional[int] = None
    liao_level: Optional[int] = None
    remark: Optional[str] = None


class TaskConfigUpdate(BaseModel):
    """更新任务配置"""

    model_config = ConfigDict(
        populate_by_name=True, validate_by_alias=True, extra="ignore"
    )

    foster: Optional[Dict[str, Any]] = Field(default=None, alias="寄养")
    xuanshang: Optional[Dict[str, Any]] = Field(default=None, alias="悬赏")
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
    )  # {enabled: bool, next_time: str, fail_delay: int}
    liao_shop: Optional[Dict[str, Any]] = Field(default=None, alias="寮商店")
    liao_coin: Optional[Dict[str, Any]] = Field(default=None, alias="领取寮金币")
    daily_summon: Optional[Dict[str, Any]] = Field(default=None, alias="每日一抽")
    weekly_shop: Optional[Dict[str, Any]] = Field(default=None, alias="每周商店")
    miwen: Optional[Dict[str, Any]] = Field(default=None, alias="秘闻")
    # 起号任务字段
    init_collect_reward: Optional[Dict[str, Any]] = Field(default=None, alias="起号_领取奖励")
    init_rent_shikigami: Optional[Dict[str, Any]] = Field(default=None, alias="起号_租借式神")
    init_newbie_quest: Optional[Dict[str, Any]] = Field(default=None, alias="起号_新手任务")
    init_exp_dungeon: Optional[Dict[str, Any]] = Field(default=None, alias="起号_经验副本")
    init_collect_jinnang: Optional[Dict[str, Any]] = Field(default=None, alias="起号_领取锦囊")
    init_shikigami_train: Optional[Dict[str, Any]] = Field(default=None, alias="起号_式神养成")
    init_fanhe_upgrade: Optional[Dict[str, Any]] = Field(default=None, alias="起号_升级饭盒")
    collect_achievement: Optional[Dict[str, Any]] = Field(default=None, alias="领取成就奖励")
    weekly_share: Optional[Dict[str, Any]] = Field(default=None, alias="每周分享")
    summon_gift: Optional[Dict[str, Any]] = Field(default=None, alias="召唤礼包")
    collect_fanhe_jiuhu: Optional[Dict[str, Any]] = Field(default=None, alias="领取饭盒酒壶")
    yuhun: Optional[Dict[str, Any]] = Field(default=None, alias="御魂")
    douji: Optional[Dict[str, Any]] = Field(default=None, alias="斗技")
    duiyi_jingcai: Optional[Dict[str, Any]] = Field(default=None, alias="对弈竞猜")


class RestConfigUpdate(BaseModel):
    """更新休息配置"""

    enabled: Optional[bool] = None
    mode: Optional[str] = None  # random|custom
    start_time: Optional[str] = None  # HH:MM
    duration: Optional[int] = None  # 小时数


def _get_global_fail_delays(db: Session) -> dict:
    """从数据库读取全局默认 fail_delay 配置。"""
    from ....db.models import SystemConfig
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    return (row.default_fail_delays or {}) if row else {}


def _get_global_task_enabled(db: Session) -> dict:
    """从数据库读取全局默认任务启用配置。"""
    from ....db.models import SystemConfig
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    return (row.default_task_enabled or {}) if row else {}


def _get_default_rest_config(db: Session) -> dict:
    """从数据库读取新建账号的默认休息配置。"""
    row = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    return (row.default_rest_config or {}) if row else {}


def _merge_task_config_with_defaults(task_config: Any, fail_delays: dict = None, progress: str = "ok") -> Dict[str, Any]:
    """按"默认 + 现有配置"规则规范化任务配置。

    现有配置中已存在的任务保留原始 enabled 状态；
    现有配置中不存在的新任务，补充默认结构但 enabled 设为 False。

    Args:
        task_config: 账号现有的 task_config。
        fail_delays: 全局默认 fail_delay 配置，用于覆盖硬编码默认值。
        progress: 账号进度状态（"init" 或 "ok"），决定使用哪套默认配置。
    """
    if progress == "init":
        merged_config = deepcopy(DEFAULT_INIT_TASK_CONFIG)
    else:
        merged_config = build_default_task_config(fail_delays)

    if not isinstance(task_config, dict):
        for value in merged_config.values():
            if isinstance(value, dict):
                value["enabled"] = False
        return merged_config

    # 将不在现有配置中的任务默认禁用
    for key in merged_config:
        if key not in task_config and isinstance(merged_config[key], dict):
            merged_config[key]["enabled"] = False

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
    获取账号列表（平铺列表）
    """
    accounts = db.query(GameAccount).all()

    result = []
    need_commit = False
    fail_delays = _get_global_fail_delays(db)

    for account in accounts:
        normalized_task_config = _merge_task_config_with_defaults(
            account.task_config, fail_delays=fail_delays, progress=account.progress
        )
        if account.task_config != normalized_task_config:
            account.task_config = normalized_task_config
            account.updated_at = datetime.utcnow()
            need_commit = True

        rc = account.rest_config
        rest_config_data = {
            "enabled": bool(rc.enabled) if rc else True,
            "mode": rc.mode if rc else "random",
            "start_time": rc.rest_start if rc else None,
            "duration": rc.rest_duration if rc else 2,
        }

        result.append(
            {
                "type": "game",
                "id": account.id,
                "login_id": account.login_id,
                "level": account.level,
                "stamina": account.stamina,
                "gouyu": account.gouyu,
                "lanpiao": account.lanpiao,
                "gold": account.gold,
                "gongxun": account.gongxun,
                "xunzhang": account.xunzhang,
                "tupo_ticket": account.tupo_ticket,
                "fanhe_level": account.fanhe_level,
                "jiuhu_level": account.jiuhu_level,
                "liao_level": account.liao_level,
                "status": account.status,
                "progress": account.progress,
                "current_task": account.current_task,
                "task_config": normalized_task_config,
                "lineup_config": account.lineup_config or {},
                "shikigami_config": merge_shikigami_with_defaults(account.shikigami_config or {}),
                "explore_progress": account.explore_progress or {},
                "remark": account.remark or "",
                "rest_config": rest_config_data,
            }
        )

    if need_commit:
        db.commit()

    return result


@router.post("/game")
async def create_game_account(
    account: GameAccountCreate, db: Session = Depends(get_db)
):
    """
    添加游戏账号
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
        level=account.level,
        stamina=account.stamina,
        progress="ok",
        status=AccountStatus.ACTIVE,
        task_config=build_default_task_config(_get_global_fail_delays(db), _get_global_task_enabled(db)),
        explore_progress=build_default_explore_progress(),
    )
    db.add(game_account)
    db.flush()  # 获取 game_account.id

    # 创建默认休息配置
    default_rest = _get_default_rest_config(db)
    rest_config = AccountRestConfig(
        account_id=game_account.id,
        enabled=1 if default_rest.get("enabled", False) else 0,
        mode=default_rest.get("mode", "random"),
        rest_start=default_rest.get("start_time"),
        rest_duration=default_rest.get("duration", 2),
    )
    db.add(rest_config)
    db.commit()
    db.refresh(game_account)

    logger.info(f"创建游戏账号: {account.login_id}")

    return {
        "message": "游戏账号创建成功",
        "account": {
            "id": game_account.id,
            "login_id": game_account.login_id,
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
        old_progress = account.progress
        account.progress = update.progress
        # progress 发生变化时切换 task_config
        if old_progress != account.progress:
            if account.progress == "ok":
                account.task_config = build_default_task_config(_get_global_fail_delays(db), _get_global_task_enabled(db))
            else:
                account.task_config = deepcopy(DEFAULT_INIT_TASK_CONFIG)
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(account, "task_config")
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
    if update.gongxun is not None:
        account.gongxun = update.gongxun
    if update.xunzhang is not None:
        account.xunzhang = update.xunzhang
    if update.tupo_ticket is not None:
        account.tupo_ticket = update.tupo_ticket
    if update.fanhe_level is not None:
        account.fanhe_level = update.fanhe_level
    if update.jiuhu_level is not None:
        account.jiuhu_level = update.jiuhu_level
    if update.liao_level is not None:
        account.liao_level = update.liao_level

    account.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"更新账号 {account.login_id} 信息")

    return {"message": "账号更新成功", "task_config": account.task_config}


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

    merged_config = _merge_task_config_with_defaults(account.task_config, fail_delays=_get_global_fail_delays(db), progress=account.progress)

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


@router.get("/{account_id}/rest-config")
async def get_rest_config(account_id: int, db: Session = Depends(get_db)):
    """
    获取休息配置
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    rc = (
        db.query(AccountRestConfig)
        .filter(AccountRestConfig.account_id == account_id)
        .first()
    )

    return {
        "enabled": bool(rc.enabled) if rc else True,
        "mode": rc.mode if rc else "random",
        "start_time": rc.rest_start if rc else None,
        "duration": rc.rest_duration if rc else 2,
    }


def _generate_rest_plan_for_today(account_id, rc, bj_now, today_str):
    """为账号生成当日休息计划，逻辑与 Feeder._ensure_daily_rest_plans 保持一致。"""
    if rc.mode == "custom" and rc.rest_start and rc.rest_duration:
        start_time = rc.rest_start
        duration_hours = float(rc.rest_duration)
        start_dt = datetime.strptime(f"{today_str} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=duration_hours)
    else:
        # random 模式：在当前时间到 23:00 之间随机生成 2-3 小时时段
        duration_hours = random.uniform(2, 3)
        bj_now_naive = bj_now.replace(tzinfo=None)
        effective_earliest = max(
            datetime.combine(bj_now.date(), time(7, 0)),
            bj_now_naive,
        )
        latest_start_dt = datetime.combine(bj_now.date(), time(23, 0)) - timedelta(hours=duration_hours)
        if latest_start_dt < effective_earliest:
            # 剩余时间不足 2 小时，无法生成
            return None
        total_minutes = max(
            int((latest_start_dt - effective_earliest).total_seconds() // 60),
            0,
        )
        start_dt = effective_earliest + timedelta(minutes=random.randint(0, total_minutes))
        start_time = start_dt.strftime("%H:%M")
        end_dt = min(
            start_dt + timedelta(hours=duration_hours),
            datetime.combine(bj_now.date(), time(23, 0)),
        )

    return RestPlan(
        account_id=account_id,
        date=today_str,
        start_time=start_time,
        end_time=end_dt.strftime("%H:%M"),
    )


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
    if config.enabled is not None:
        rest_config.enabled = 1 if config.enabled else 0
    if config.mode is not None:
        rest_config.mode = config.mode
    if config.mode == "custom" or (config.mode is None and rest_config.mode == "custom"):
        if config.start_time is not None:
            rest_config.rest_start = config.start_time
        if config.duration is not None:
            rest_config.rest_duration = config.duration
    rest_config.updated_at = datetime.utcnow()

    from ....core.timeutils import now_beijing
    bj_now = now_beijing()
    today_str = bj_now.date().isoformat()

    # 删除当日旧 RestPlan（禁用或配置变更都需要清除）
    db.query(RestPlan).filter(
        RestPlan.account_id == account_id,
        RestPlan.date == today_str,
    ).delete(synchronize_session=False)

    # 启用时：按新配置立即生成当日 RestPlan
    if rest_config.enabled == 1:
        plan = _generate_rest_plan_for_today(account_id, rest_config, bj_now, today_str)
        if plan:
            db.add(plan)

    db.commit()

    logger.info(f"更新账号 {account.login_id} 休息配置")

    return {
        "message": "休息配置更新成功",
        "config": {
            "enabled": bool(rest_config.enabled),
            "mode": rest_config.mode,
            "start_time": rest_config.rest_start,
            "duration": rest_config.rest_duration,
        },
    }


@router.get("/{account_id}/rest-plan")
async def get_rest_plan(account_id: int, db: Session = Depends(get_db)):
    """
    获取今日休息计划（若已启用但无计划，按需自动生成）
    """
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    # 检查休息是否启用
    rest_config = (
        db.query(AccountRestConfig)
        .filter(AccountRestConfig.account_id == account_id)
        .first()
    )
    if rest_config and rest_config.enabled == 0:
        return {"message": "休息功能已关闭"}

    from ....core.timeutils import now_beijing
    bj_now = now_beijing()
    today = bj_now.date().isoformat()
    plan = (
        db.query(RestPlan)
        .filter(RestPlan.account_id == account_id, RestPlan.date == today)
        .first()
    )

    # 按需生成：rest 已启用但当日无计划时自动创建
    if not plan:
        if not rest_config:
            rest_config = AccountRestConfig(account_id=account_id)
            db.add(rest_config)
            db.flush()
        plan = _generate_rest_plan_for_today(account_id, rest_config, bj_now, today)
        if plan:
            db.add(plan)
            db.commit()
        else:
            return {"message": "今日剩余时间不足，无法生成休息计划"}

    return {"date": plan.date, "start_time": plan.start_time, "end_time": plan.end_time}


@router.post("/init-status")
async def update_init_status(data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    执行器更新起号状态（内部API）
    """
    account_id = data.get("account_id")
    init_status = data.get("status")
    level = data.get("level", 1)
    message = data.get("message", "")

    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 更新账号状态
    account.status = init_status
    old_progress = account.progress
    if init_status == AccountStatus.ACTIVE:
        account.progress = "ok"
    else:
        account.progress = "init"

    # progress 发生变化时切换 task_config
    if old_progress != account.progress:
        if account.progress == "ok":
            account.task_config = build_default_task_config(_get_global_fail_delays(db), _get_global_task_enabled(db))
        else:
            account.task_config = deepcopy(DEFAULT_INIT_TASK_CONFIG)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(account, "task_config")

    if level:
        account.level = level

    account.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"更新起号状态: 账号={account.login_id}, 状态={init_status}, 消息={message}")

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
    删除单个游戏账号及其关联数据
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


# ───────── 式神状态配置 ─────────


class ShikigamiConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    zuofu: Optional[Dict[str, Any]] = Field(default=None, alias="座敷童子")


@router.get("/{account_id}/shikigami-config")
async def get_shikigami_config(account_id: int, db: Session = Depends(get_db)):
    """获取账号式神状态配置"""
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    merged = merge_shikigami_with_defaults(account.shikigami_config or {})
    return merged


@router.put("/{account_id}/shikigami-config")
async def update_shikigami_config(
    account_id: int, config: ShikigamiConfigUpdate, db: Session = Depends(get_db)
):
    """更新账号式神状态配置"""
    account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    current = account.shikigami_config or {}
    update_dict = config.model_dump(exclude_unset=True, by_alias=True)

    for key, value in update_dict.items():
        if value is not None and isinstance(value, dict):
            base = current.get(key, {})
            if not isinstance(base, dict):
                base = {}
            base.update(value)
            current[key] = base

    from sqlalchemy.orm.attributes import flag_modified

    account.shikigami_config = current
    flag_modified(account, "shikigami_config")
    account.updated_at = datetime.utcnow()
    db.commit()

    merged = merge_shikigami_with_defaults(account.shikigami_config)
    logger.info(f"更新账号 {account.login_id} 式神配置")

    return {"message": "式神配置更新成功", "config": merged}
