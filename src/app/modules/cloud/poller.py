"""
Cloud task poller: pull jobs from cloud and feed local executor.
"""
from __future__ import annotations

import asyncio
import platform
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional

from ...core.config import settings, BASE_DIR
from ...core.constants import TaskType
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import GameAccount
from ..executor.service import executor_service
from ..executor.types import TaskIntent
from .client import CloudApiError, cloud_api_client
from .runtime import runtime_mode_state


@dataclass
class DeferredJob:
    """入队失败暂存的任务信息"""
    job_id: int
    account_id: int
    task_type: TaskType
    intent_payload: dict
    cloud_user_id: int = 0
    login_id: str = ""


def _resolve_node_id() -> str:
    """Resolve node_id: prefer config, then persisted file, else generate and persist."""
    configured = (settings.cloud_agent_node_id or "").strip()
    if configured and configured != "local-node":
        return configured

    node_id_file = Path(BASE_DIR) / "config" / "node_id"
    if node_id_file.exists():
        stored = node_id_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    hostname = platform.node() or "unknown"
    rand_suffix = secrets.token_hex(4)
    generated = f"{hostname}-{rand_suffix}"

    node_id_file.parent.mkdir(parents=True, exist_ok=True)
    node_id_file.write_text(generated, encoding="utf-8")
    return generated


def _resolve_local_account(cloud_user_id: int, login_id: str) -> Optional[int]:
    """Resolve cloud user to local GameAccount.id.

    Strategy:
    1. Find by cloud_user_id (fast path for already-mapped accounts)
    2. Find by login_id
    3. Auto-create GameAccount if login_id is valid
    """
    with SessionLocal() as db:
        # 1. 按 cloud_user_id 查找（已有映射）
        account = (
            db.query(GameAccount)
            .filter(GameAccount.cloud_user_id == cloud_user_id)
            .first()
        )
        if account:
            return account.id

        # 2. 按 login_id 查找
        if login_id:
            account = (
                db.query(GameAccount)
                .filter(GameAccount.login_id == login_id)
                .first()
            )
            if account:
                # 补充绑定 cloud_user_id
                account.cloud_user_id = cloud_user_id
                db.commit()
                return account.id

            # 3. 自动创建
            try:
                new_account = GameAccount(
                    login_id=login_id,
                    cloud_user_id=cloud_user_id,
                    status=1,
                    progress="ok",
                )
                db.add(new_account)
                db.commit()
                db.refresh(new_account)
                logger.info(
                    "Auto-created local GameAccount: id={}, login_id={}, cloud_user_id={}",
                    new_account.id, login_id, cloud_user_id,
                )
                return new_account.id
            except Exception:
                db.rollback()
                # 并发竞态：重新查询
                account = (
                    db.query(GameAccount)
                    .filter(GameAccount.login_id == login_id)
                    .first()
                )
                if account:
                    account.cloud_user_id = cloud_user_id
                    db.commit()
                    return account.id
    return None


class CloudTaskPoller:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._agent_token: str = ""
        self._node_id = _resolve_node_id()
        self._poll_interval = max(1, int(settings.cloud_poll_interval_sec or 5))
        self._lease_seconds = max(30, int(settings.cloud_lease_sec or 90))
        self._failure_count = 0
        self._last_error: Optional[str] = None
        self._last_poll_at: Optional[str] = None
        self._account_jobs: Dict[int, Deque[int]] = defaultdict(deque)
        self._deferred_jobs: Dict[int, List[DeferredJob]] = defaultdict(list)
        self._job_meta: Dict[int, dict] = {}  # job_id -> {task_type, login_id, account_id}
        self._map_lock = asyncio.Lock()
        self.log = logger.bind(module="CloudTaskPoller")

    async def verify_agent_login(self, username: str, password: str) -> None:
        """Verify credentials by performing an agent login against the cloud API."""
        if not cloud_api_client.configured():
            raise CloudApiError("CLOUD_API_BASE_URL 未配置")
        await cloud_api_client.agent_login(
            username=username,
            password=password,
            node_id=self._node_id,
        )

    # Keep old name as alias for backward compatibility with auth.py
    async def verify_manager_login(self, username: str, password: str) -> None:
        await self.verify_agent_login(username=username, password=password)

    async def start(self) -> None:
        if self._running:
            return
        if not cloud_api_client.configured():
            raise CloudApiError("CLOUD_API_BASE_URL 未配置")

        username, password = runtime_mode_state.get_manager_credentials()
        if not username or not password:
            raise CloudApiError("云端管理员账号未配置，请先登录")

        await self._ensure_agent_login(username=username, password=password)
        executor_service.register_batch_done_listener(self._on_batch_done)
        executor_service.register_intent_done_listener(self._on_intent_done)
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_deferred_loop())
        self.log.info("CloudTaskPoller started, node_id={}", self._node_id)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        executor_service.unregister_batch_done_listener(self._on_batch_done)
        executor_service.unregister_intent_done_listener(self._on_intent_done)
        async with self._map_lock:
            self._account_jobs.clear()
            self._deferred_jobs.clear()
            self._job_meta.clear()
        self.log.info("CloudTaskPoller stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "configured": cloud_api_client.configured(),
            "node_id": self._node_id,
            "poll_interval_sec": self._poll_interval,
            "lease_seconds": self._lease_seconds,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
            "last_poll_at": self._last_poll_at,
            "tracked_accounts": len(self._account_jobs),
            "deferred_jobs": sum(len(v) for v in self._deferred_jobs.values()),
            "tracked_job_details": self._get_tracked_job_details(),
            "deferred_job_details": self._get_deferred_job_details(),
        }

    def _get_tracked_job_details(self) -> list:
        """返回当前正在执行的 cloud job 列表。"""
        details = []
        for account_id, job_ids in self._account_jobs.items():
            for job_id in job_ids:
                meta = self._job_meta.get(job_id, {})
                details.append({
                    "job_id": job_id,
                    "account_id": account_id,
                    "task_type": meta.get("task_type", ""),
                    "login_id": meta.get("login_id", ""),
                    "status": "running",
                })
        return details

    def _get_deferred_job_details(self) -> list:
        """返回缓冲等待中的 cloud job 列表。"""
        details = []
        for account_id, jobs in self._deferred_jobs.items():
            for d in jobs:
                details.append({
                    "job_id": d.job_id,
                    "account_id": d.account_id,
                    "task_type": d.task_type.value if hasattr(d.task_type, "value") else str(d.task_type),
                    "login_id": d.login_id,
                    "status": "deferred",
                })
        return details

    async def _ensure_agent_login(self, username: str, password: str) -> None:
        self._agent_token = await cloud_api_client.agent_login(
            username=username,
            password=password,
            node_id=self._node_id,
        )

    async def _loop(self) -> None:
        while self._running:
            try:
                username, password = runtime_mode_state.get_manager_credentials()
                if not username or not password:
                    raise CloudApiError("云端管理员账号为空")

                if not self._agent_token:
                    await self._ensure_agent_login(username=username, password=password)

                # 无可用 worker 时跳过轮询（仅有 scan 模拟器时 _workers 为空）
                if not executor_service._workers:
                    if not getattr(self, '_no_worker_warned', False):
                        self.log.warning("executor 没有可用 worker（无 general/coop/init 模拟器），跳过云端任务轮询")
                        self._no_worker_warned = True
                    await asyncio.sleep(self._poll_interval)
                    continue
                self._no_worker_warned = False

                # 有缓冲任务时跳过拉取，避免重复领取
                if self._deferred_jobs:
                    await asyncio.sleep(self._poll_interval)
                    continue

                jobs = await cloud_api_client.poll_jobs(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    limit=10,
                    lease_seconds=self._lease_seconds,
                )
                self._last_poll_at = datetime.utcnow().isoformat()

                for job in jobs:
                    await self._handle_job(job)

                self._failure_count = 0
                self._last_error = None
                await asyncio.sleep(0.3 if jobs else self._poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._failure_count += 1
                self._last_error = str(exc)
                self.log.warning(f"cloud poll error: {exc}")
                if "invalid token" in str(exc).lower() or "401" in str(exc):
                    self._agent_token = ""
                await asyncio.sleep(min(30, 2 ** min(self._failure_count, 5)))

    async def _handle_job(self, job: dict) -> None:
        if not isinstance(job, dict):
            return
        job_id = int(job.get("id") or job.get("ID") or 0)
        task_type_value = job.get("task_type") or job.get("TaskType")
        payload = job.get("payload") or job.get("Payload")
        if not isinstance(payload, dict):
            payload = {}

        cloud_user_id = job.get("user_id") or job.get("UserID")
        account_id = None

        # 先获取 full_config（需要其中的 login_id 来解析本地账号）
        full_config = {}
        login_id = ""
        cloud_uid = 0
        if cloud_user_id is not None:
            try:
                cloud_uid = int(cloud_user_id)
            except (TypeError, ValueError):
                cloud_uid = 0

        if cloud_uid > 0:
            try:
                full_config = await cloud_api_client.get_full_config(
                    user_id=cloud_uid,
                    token=self._agent_token,
                )
                login_id = str(full_config.get("login_id", "") or "")
            except Exception as exc:
                self.log.warning(f"get_full_config failed for user_id={cloud_uid}: {exc}")

            # 通过 cloud_user_id + login_id 解析本地账号（自动创建）
            local_id = _resolve_local_account(cloud_uid, login_id)
            if local_id is not None:
                account_id = local_id
            else:
                await self._report_fail(
                    job_id,
                    f"无法解析本地账号: 云端用户ID={cloud_uid}, 登录ID={login_id}",
                    "LOCAL_ACCOUNT_NOT_MAPPED",
                )
                return

        # 回退：从 payload 取（兼容手动/外部注入的任务）
        if account_id is None:
            account_id = payload.get("local_account_id") or payload.get("account_id")

        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            await self._report_fail(job_id, "缺少本地账号ID", "LOCAL_ACCOUNT_MISSING")
            return

        try:
            task_type = TaskType(task_type_value)
        except Exception:
            await self._report_fail(job_id, f"不支持的任务类型: {task_type_value}", "TASK_TYPE_INVALID")
            return

        intent_payload = dict(payload)
        intent_payload["cloud_job_id"] = job_id
        if cloud_user_id is not None:
            intent_payload["cloud_user_id"] = cloud_user_id
        # Inject configs into payload for executor use
        if full_config.get("rest_config"):
            intent_payload["rest_config"] = full_config["rest_config"]
        if full_config.get("lineup_config"):
            intent_payload["lineup_config"] = full_config["lineup_config"]
        if full_config.get("shikigami_config"):
            intent_payload["shikigami_config"] = full_config["shikigami_config"]
        if full_config.get("task_config"):
            intent_payload["cloud_task_config"] = full_config["task_config"]
        enqueued = executor_service.enqueue(
            account_id=account_id,
            task_type=task_type,
            payload=intent_payload,
        )
        if not enqueued:
            # 执行器正忙，缓冲任务等批次完成后重试
            deferred = DeferredJob(
                job_id=job_id,
                account_id=account_id,
                task_type=task_type,
                intent_payload=intent_payload,
                cloud_user_id=cloud_uid,
                login_id=login_id,
            )
            async with self._map_lock:
                self._deferred_jobs[account_id].append(deferred)
                self._job_meta[job_id] = {
                    "task_type": task_type.value,
                    "login_id": login_id,
                    "account_id": account_id,
                }
            self.log.info(f"任务缓冲等待执行: job_id={job_id}, account={account_id}, type={task_type_value}")
            # 发心跳保持租约
            try:
                await cloud_api_client.report_job_heartbeat(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    job_id=job_id,
                    lease_seconds=self._lease_seconds,
                    message="本地队列繁忙，保持租约",
                )
            except Exception:
                pass
            return

        async with self._map_lock:
            self._account_jobs[account_id].append(job_id)
            self._job_meta[job_id] = {
                "task_type": task_type.value,
                "login_id": login_id,
                "account_id": account_id,
            }

        await cloud_api_client.report_job_start(
            agent_token=self._agent_token,
            node_id=self._node_id,
            job_id=job_id,
            lease_seconds=self._lease_seconds,
            message=f"已入队本地账号 {account_id}",
        )

    async def _on_intent_done(
        self,
        account_id: int,
        intent: TaskIntent,
        success: bool,
    ) -> None:
        """单个 intent 完成后立即上报对应的 cloud job。"""
        if not self._running:
            return

        cloud_job_id = (intent.payload or {}).get("cloud_job_id")
        if not cloud_job_id:
            return  # 非云端任务，跳过

        cloud_job_id = int(cloud_job_id)

        # 从 _account_jobs 中移除该 job_id（标记为已上报）
        async with self._map_lock:
            queue = self._account_jobs.get(account_id)
            if queue and cloud_job_id in queue:
                queue.remove(cloud_job_id)
                if not queue:
                    self._account_jobs.pop(account_id, None)
            self._job_meta.pop(cloud_job_id, None)

        # 收集账号状态
        result = self._collect_account_result(account_id, success)

        task_name = intent.task_type.value if hasattr(intent.task_type, "value") else str(intent.task_type)
        message = f"任务{'完成' if success else '失败'}: {task_name}, 账号={account_id}"

        try:
            if success:
                await cloud_api_client.report_job_complete(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    job_id=cloud_job_id,
                    message=message,
                    result=result,
                )
            else:
                await cloud_api_client.report_job_fail(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    job_id=cloud_job_id,
                    message=message,
                    error_code="LOCAL_BATCH_FAILED",
                    result=result,
                )
            self.log.info(f"已上报云端 job: job_id={cloud_job_id}, task={task_name}, success={success}")
        except Exception as exc:
            self.log.warning(f"上报云端 job 失败: job_id={cloud_job_id}, err={exc}")

        # Per-intent 日志上报
        cloud_uid = (intent.payload or {}).get("cloud_user_id")
        if cloud_uid:
            try:
                ts = (intent.started_at or intent.enqueue_time).isoformat() + "Z"
                log_entry = {
                    "type": task_name,
                    "level": "INFO" if success else "WARNING",
                    "message": f"{'执行成功' if success else '执行失败'}: {task_name}",
                    "ts": ts,
                }
                await cloud_api_client.report_logs(
                    user_id=int(cloud_uid),
                    logs=[log_entry],
                    token=self._agent_token,
                )
            except Exception as exc:
                self.log.warning(f"上报云端日志失败: user_id={cloud_uid}, err={exc}")

    async def _on_batch_done(
        self,
        account_id: int,
        success: bool,
        intents: List[TaskIntent],
    ) -> None:
        if not self._running:
            return

        # 清理 _account_jobs 中可能残留的条目
        # （正常情况下应已被 _on_intent_done 清空，残留说明有未执行的 intent）
        async with self._map_lock:
            remaining = list(self._account_jobs.pop(account_id, deque()))
            for job_id in remaining:
                self._job_meta.pop(job_id, None)

        # 如果有残留的 job_id（abort 后未执行的 intent），补报为失败
        if remaining:
            result = self._collect_account_result(account_id, False)
            for job_id in remaining:
                try:
                    await cloud_api_client.report_job_fail(
                        agent_token=self._agent_token,
                        node_id=self._node_id,
                        job_id=job_id,
                        message=f"批次中断，未执行的任务补报失败, 账号={account_id}",
                        error_code="LOCAL_BATCH_FAILED",
                        result=result,
                    )
                except Exception as exc:
                    self.log.warning(f"补报云端 job 失败: job_id={job_id}, err={exc}")

        # 尝试入队缓冲的任务
        await self._retry_deferred(account_id)

    def _collect_account_result(self, account_id: int, success: bool) -> dict:
        """Read local GameAccount after execution and build result dict for cloud sync."""
        _STATUS_MAP = {1: "active", 2: "invalid", 3: "cangbaoge"}

        try:
            with SessionLocal() as db:
                account = db.query(GameAccount).filter(GameAccount.id == account_id).first()
                if not account:
                    return {"current_task": ""}
        except Exception:
            return {"current_task": ""}

        result: dict = {
            "account_status": _STATUS_MAP.get(account.status, "active"),
            "login_id": account.login_id or "",
            "current_task": "",
        }

        # Only sync assets and explore_progress on success (data may be incomplete on failure)
        if success:
            result["assets"] = {
                "level": account.level or 0,
                "stamina": account.stamina or 0,
                "gouyu": account.gouyu or 0,
                "lanpiao": account.lanpiao or 0,
                "gold": account.gold or 0,
                "gongxun": account.gongxun or 0,
                "xunzhang": account.xunzhang or 0,
                "tupo_ticket": account.tupo_ticket or 0,
                "fanhe_level": account.fanhe_level or 0,
                "jiuhu_level": account.jiuhu_level or 0,
                "liao_level": account.liao_level or 0,
            }
            if account.explore_progress:
                result["explore_progress"] = account.explore_progress

        return result

    async def _retry_deferred(self, account_id: int) -> None:
        """批次完成后，尝试入队该账号的缓冲任务。"""
        async with self._map_lock:
            pending = self._deferred_jobs.pop(account_id, [])
        if not pending:
            return

        for deferred in pending:
            enqueued = executor_service.enqueue(
                account_id=deferred.account_id,
                task_type=deferred.task_type,
                payload=deferred.intent_payload,
            )
            if enqueued:
                async with self._map_lock:
                    self._account_jobs[deferred.account_id].append(deferred.job_id)
                try:
                    await cloud_api_client.report_job_start(
                        agent_token=self._agent_token,
                        node_id=self._node_id,
                        job_id=deferred.job_id,
                        lease_seconds=self._lease_seconds,
                        message=f"缓冲任务开始执行, 账号={deferred.account_id}",
                    )
                except Exception:
                    pass
                self.log.info(f"缓冲任务入队成功: job_id={deferred.job_id}, account={deferred.account_id}")
            else:
                # 仍然无法入队，放回缓冲
                async with self._map_lock:
                    self._deferred_jobs[account_id].append(deferred)
                self.log.warning(f"缓冲任务仍无法入队: job_id={deferred.job_id}")

    async def _heartbeat_deferred_loop(self) -> None:
        """定期对缓冲任务发心跳，防止租约超时。"""
        while self._running:
            try:
                await asyncio.sleep(30)
                async with self._map_lock:
                    all_deferred = [
                        d for jobs in self._deferred_jobs.values() for d in jobs
                    ]
                for deferred in all_deferred:
                    try:
                        await cloud_api_client.report_job_heartbeat(
                            agent_token=self._agent_token,
                            node_id=self._node_id,
                            job_id=deferred.job_id,
                            lease_seconds=self._lease_seconds,
                            message="等待执行器空闲",
                        )
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def _report_fail(self, job_id: int, message: str, error_code: str) -> None:
        if job_id <= 0 or not self._agent_token:
            return
        try:
            await cloud_api_client.report_job_fail(
                agent_token=self._agent_token,
                node_id=self._node_id,
                job_id=job_id,
                message=message,
                error_code=error_code,
            )
        except Exception as exc:
            self.log.warning(f"report cloud fail failed: job_id={job_id}, err={exc}")


cloud_task_poller = CloudTaskPoller()


__all__ = ["cloud_task_poller", "CloudTaskPoller"]
