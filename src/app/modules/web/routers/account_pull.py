"""
账号抓取API
从模拟器中抓取阴阳师游戏账号登录数据
"""
import shutil
from pathlib import Path
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ....db.base import get_db
from ....db.models import AccountRestConfig, Emulator, GameAccount, SystemConfig
from ....core.logger import logger
from ....core.config import settings
from ....core.constants import AccountStatus, build_default_task_config, build_default_explore_progress
from ...emu.adb import Adb
from ...emu.adapter import AdapterConfig, EmulatorAdapter


router = APIRouter(prefix="/api/account-pull", tags=["account-pull"])

# 游戏包名（渠道包）
PKG_NAME = "com.netease.onmyoji.wyzymnqsd_cps"

# 数据保存目录
GOUXIE_DIR = "gouxielogindata"
PUTONG_DIR = "putonglogindata"


class PullRequest(BaseModel):
    """抓取请求"""
    emulator_id: int
    pull_type: Literal["gouxie", "putong"]  # 勾协账号 / 普通账号
    account_id: str  # 账号ID，作为文件夹名


class PullResponse(BaseModel):
    """抓取响应"""
    success: bool
    message: str
    files: List[str] = []


class PushResponse(BaseModel):
    """上传响应"""
    success: bool
    message: str
    pushed_items: List[str] = []


class AccountInfo(BaseModel):
    """已抓取账号信息"""
    account_id: str
    pull_type: str
    path: str


class DeleteLoginDataResponse(BaseModel):
    """删除模拟器登录数据响应"""
    success: bool
    message: str
    deleted_paths: List[str] = []


@router.post("/pull", response_model=PullResponse)
async def pull_account(
    req: PullRequest,
    db: Session = Depends(get_db)
):
    """
    从模拟器抓取账号数据

    抓取数据源：
    1. /data/user/0/{PKG}/shared_prefs - 账号凭证
    2. sdcard/Android/data/{PKG}/files/netease/onmyoji/Documents/clientconfig - 客户端配置
    """
    # 获取模拟器信息
    emulator = db.query(Emulator).filter(Emulator.id == req.emulator_id).first()
    if not emulator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟器不存在"
        )

    # 检查模拟器状态
    if emulator.state != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="模拟器未连接，请先连接模拟器"
        )

    # 确定保存目录
    base_dir = GOUXIE_DIR if req.pull_type == "gouxie" else PUTONG_DIR
    save_dir = Path(base_dir) / req.account_id

    # 创建目录
    save_dir.mkdir(parents=True, exist_ok=True)

    # 获取ADB路径
    syscfg = db.query(SystemConfig).first()
    adb_path = (syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path)
    adb = Adb(adb_path)
    addr = emulator.adb_addr

    pulled_files = []
    errors = []

    try:
        # 尝试获取root权限（用于读取 /data 目录）
        adb.root(addr)

        # 抓取 shared_prefs（账号凭证）
        shared_prefs_remote = f"/data/user/0/{PKG_NAME}/shared_prefs"
        shared_prefs_local = save_dir / "shared_prefs"

        # 清理旧数据，避免 adb pull 产生 shared_prefs/shared_prefs 嵌套
        if shared_prefs_local.exists():
            shutil.rmtree(shared_prefs_local)

        ok, msg = adb.pull(addr, shared_prefs_remote, str(save_dir), timeout=120.0)
        if ok:
            pulled_files.append("shared_prefs")
            logger.info(f"抓取 shared_prefs 成功: {msg}")
        else:
            errors.append(f"shared_prefs: {msg}")
            logger.warning(f"抓取 shared_prefs 失败: {msg}")

        # 抓取 clientconfig（客户端配置），直接保存到账号目录下（与 shared_prefs 同级）
        clientconfig_remote = f"/sdcard/Android/data/{PKG_NAME}/files/netease/onmyoji/Documents/clientconfig"
        clientconfig_local = str(save_dir)  # 直接拉到账号目录，adb pull 会创建 clientconfig 文件/文件夹

        ok, msg = adb.pull(addr, clientconfig_remote, clientconfig_local, timeout=120.0)
        if ok:
            pulled_files.append("clientconfig")
            logger.info(f"抓取 clientconfig 成功: {msg}")
        else:
            errors.append(f"clientconfig: {msg}")
            logger.warning(f"抓取 clientconfig 失败: {msg}")

        if not pulled_files:
            # 如果都失败了，删除空目录
            shutil.rmtree(save_dir, ignore_errors=True)
            return PullResponse(
                success=False,
                message=f"抓取失败: {'; '.join(errors)}",
                files=[]
            )

        return PullResponse(
            success=True,
            message=f"抓取成功，保存到 {save_dir}" + (f"（部分失败: {'; '.join(errors)}）" if errors else ""),
            files=pulled_files
        )

    except Exception as e:
        logger.error(f"抓取账号数据失败: {e}")
        # 清理可能创建的空目录
        if save_dir.exists() and not any(save_dir.iterdir()):
            shutil.rmtree(save_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"抓取失败: {str(e)}"
        )


@router.post("/push", response_model=PushResponse)
async def push_account_data(
    req: PullRequest,
    db: Session = Depends(get_db)
):
    """
    将本地账号登录数据上传到选中模拟器。

    上传内容：
    1. shared_prefs（文件夹）
    2. clientconfig（文件/文件夹）
    """
    emulator = db.query(Emulator).filter(Emulator.id == req.emulator_id).first()
    if not emulator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟器不存在"
        )

    if emulator.state != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="模拟器未连接，请先连接模拟器"
        )

    base_dir = GOUXIE_DIR if req.pull_type == "gouxie" else PUTONG_DIR
    local_base = Path(base_dir) / req.account_id
    if not local_base.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"本地账号数据不存在: {local_base}"
        )

    shared_prefs_local = local_base / "shared_prefs"
    clientconfig_local = local_base / "clientconfig"
    pushed_items = []
    if shared_prefs_local.exists():
        pushed_items.append("shared_prefs")
    if clientconfig_local.exists():
        pushed_items.append("clientconfig")

    if not pushed_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="本地数据缺失：未找到 shared_prefs/clientconfig"
        )

    syscfg = db.query(SystemConfig).first()
    adb_path = (syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path)

    cfg = AdapterConfig(
        adb_path=adb_path,
        adb_addr=emulator.adb_addr,
        pkg_name=PKG_NAME,
        ipc_dll_path=(syscfg.ipc_dll_path if syscfg else "") or "",
        mumu_manager_path=(syscfg.mumu_manager_path if syscfg else "") or "",
        nemu_folder=(syscfg.nemu_folder if syscfg else "") or "",
        instance_id=getattr(emulator, "instance_id", None),
        activity_name=(syscfg.activity_name if syscfg else None) or ".MainActivity",
    )

    try:
        adapter = EmulatorAdapter(cfg)
        ok = adapter.push_login_data(req.account_id, data_dir=base_dir)
        if not ok:
            return PushResponse(
                success=False,
                message="上传失败，请检查 shared_prefs/clientconfig 及 ADB 权限",
                pushed_items=pushed_items,
            )

        logger.info(
            f"上传账号数据成功: emulator={emulator.name}({emulator.adb_addr}), "
            f"type={req.pull_type}, account_id={req.account_id}, items={pushed_items}"
        )
        return PushResponse(
            success=True,
            message=f"上传成功（{', '.join(pushed_items)}）",
            pushed_items=pushed_items,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传账号数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传失败: {str(e)}"
        )


@router.get("/list/{pull_type}")
async def list_accounts(
    pull_type: Literal["gouxie", "putong"]
):
    """
    列出已抓取的账号
    """
    base_dir = GOUXIE_DIR if pull_type == "gouxie" else PUTONG_DIR
    base_path = Path(base_dir)

    accounts = []

    if base_path.exists():
        for item in base_path.iterdir():
            if item.is_dir():
                accounts.append({
                    "account_id": item.name,
                    "pull_type": pull_type,
                    "path": str(item),
                    "has_shared_prefs": (item / "shared_prefs").exists(),
                    "has_clientconfig": (item / "clientconfig").exists()
                })

    return accounts


@router.delete("/delete/{pull_type}/{account_id}")
async def delete_account(
    pull_type: Literal["gouxie", "putong"],
    account_id: str
):
    """
    删除已抓取的账号数据
    """
    base_dir = GOUXIE_DIR if pull_type == "gouxie" else PUTONG_DIR
    account_path = Path(base_dir) / account_id

    if not account_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号数据不存在"
        )

    try:
        shutil.rmtree(account_path)
        logger.info(f"删除账号数据: {account_path}")
        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除账号数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败: {str(e)}"
        )


@router.delete("/device-login-data/{emulator_id}", response_model=DeleteLoginDataResponse)
async def delete_device_login_data(
    emulator_id: int,
    delete_clientconfig: bool = False,
    db: Session = Depends(get_db)
):
    """
    删除选中模拟器中的登录数据。

    参考旧版 PyQt 工具逻辑：
    - 默认只删除 `shared_prefs`
    - `clientconfig` 默认不删除（可通过参数 `delete_clientconfig=true` 开启）
    """
    emulator = db.query(Emulator).filter(Emulator.id == emulator_id).first()
    if not emulator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟器不存在"
        )

    if emulator.state != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="模拟器未连接，请先连接模拟器"
        )

    syscfg = db.query(SystemConfig).first()
    adb_path = (syscfg.adb_path if syscfg and syscfg.adb_path else settings.adb_path)
    adb = Adb(adb_path)
    addr = emulator.adb_addr

    shared_prefs_remote = f"/data/user/0/{PKG_NAME}/shared_prefs"
    clientconfig_remote = f"/sdcard/Android/data/{PKG_NAME}/files/netease/onmyoji/Documents/clientconfig"

    deleted_paths: List[str] = []

    try:
        rooted = adb.root(addr)
        if not rooted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ADB root 失败，无法删除登录数据"
            )

        code, out = adb.shell(addr, f"rm -rf {shared_prefs_remote}", timeout=30.0)
        if code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"删除 shared_prefs 失败: {out.strip() or '未知错误'}"
            )
        deleted_paths.append(shared_prefs_remote)

        if delete_clientconfig:
            code, out = adb.shell(addr, f"rm -rf {clientconfig_remote}", timeout=30.0)
            if code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"删除 clientconfig 失败: {out.strip() or '未知错误'}"
                )
            deleted_paths.append(clientconfig_remote)

        logger.info(
            f"删除模拟器登录数据: emulator={emulator.name}({addr}), "
            f"paths={deleted_paths}, delete_clientconfig={delete_clientconfig}"
        )
        message = "删除成功" if delete_clientconfig else "删除成功（已按默认逻辑仅删除 shared_prefs）"
        return DeleteLoginDataResponse(
            success=True,
            message=message,
            deleted_paths=deleted_paths,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模拟器登录数据失败: emulator_id={emulator_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败: {str(e)}"
        )


class BatchCreateResponse(BaseModel):
    """批量建号响应"""
    success: bool
    message: str
    created: List[str] = []
    skipped: List[str] = []


@router.post("/batch-create", response_model=BatchCreateResponse)
async def batch_create_accounts(
    db: Session = Depends(get_db)
):
    """
    从已抓取的普通账号列表批量创建游戏账号。

    - 扫描 putonglogindata/ 目录获取所有已抓取账号 ID
    - 已存在的 login_id 自动跳过
    - 新账号的 task_config 继承系统配置的默认失败延迟
    """
    base_path = Path(PUTONG_DIR)
    if not base_path.exists():
        return BatchCreateResponse(
            success=True,
            message="无已抓取的普通账号",
            created=[],
            skipped=[],
        )

    # 收集所有已抓取的账号 ID
    pulled_ids = [item.name for item in base_path.iterdir() if item.is_dir()]
    if not pulled_ids:
        return BatchCreateResponse(
            success=True,
            message="无已抓取的普通账号",
            created=[],
            skipped=[],
        )

    # 查询数据库中已存在的 login_id
    existing_ids = {
        row.login_id
        for row in db.query(GameAccount.login_id)
        .filter(GameAccount.login_id.in_(pulled_ids))
        .all()
    }

    # 读取全局默认失败延迟和默认任务启用配置
    syscfg = db.query(SystemConfig).order_by(SystemConfig.id.asc()).first()
    fail_delays = (syscfg.default_fail_delays or {}) if syscfg else {}
    task_enabled = (syscfg.default_task_enabled or {}) if syscfg else {}
    default_rest = (syscfg.default_rest_config or {}) if syscfg else {}

    created = []
    skipped = []

    for account_id in pulled_ids:
        if account_id in existing_ids:
            skipped.append(account_id)
            continue

        game_account = GameAccount(
            login_id=account_id,
            progress="ok",
            status=AccountStatus.ACTIVE,
            task_config=build_default_task_config(fail_delays, task_enabled),
            explore_progress=build_default_explore_progress(),
        )
        db.add(game_account)
        db.flush()  # 获取 game_account.id

        # 创建默认休息配置
        rest_config = AccountRestConfig(
            account_id=game_account.id,
            enabled=1 if default_rest.get("enabled", False) else 0,
            mode=default_rest.get("mode", "random"),
            rest_start=default_rest.get("start_time"),
            rest_duration=default_rest.get("duration", 2),
        )
        db.add(rest_config)
        created.append(account_id)

    if created:
        db.commit()

    total = len(created) + len(skipped)
    message = f"共 {total} 个账号，创建 {len(created)} 个，跳过 {len(skipped)} 个"
    logger.info(f"批量建号完成: {message}")

    return BatchCreateResponse(
        success=True,
        message=message,
        created=created,
        skipped=skipped,
    )
