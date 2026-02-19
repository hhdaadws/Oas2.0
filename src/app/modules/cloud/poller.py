"""
Cloud task poller: pull jobs from cloud and feed local executor.
"""
from __future__ import annotations

import asyncio
import platform
import secrets
from collections import defaultdict, deque
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


def _lookup_local_account_id(cloud_user_id: int) -> Optional[int]:
    """Map cloud user_id to local GameAccount.id via cloud_user_id field."""
    with SessionLocal() as db:
        account = (
            db.query(GameAccount)
            .filter(GameAccount.cloud_user_id == cloud_user_id)
            .first()
        )
        if account:
            return account.id
    return None


class CloudTaskPoller:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._agent_token: str = ""
        self._node_id = _resolve_node_id()
        self._poll_interval = max(1, int(settings.cloud_poll_interval_sec or 5))
        self._lease_seconds = max(30, int(settings.cloud_lease_sec or 90))
        self._failure_count = 0
        self._last_error: Optional[str] = None
        self._last_poll_at: Optional[str] = None
        self._account_jobs: Dict[int, Deque[int]] = defaultdict(deque)
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
        self._running = True
        self._task = asyncio.create_task(self._loop())
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
        executor_service.unregister_batch_done_listener(self._on_batch_done)
        async with self._map_lock:
            self._account_jobs.clear()
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
        }

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

        # Resolve local account_id from cloud user_id
        # Priority: payload.local_account_id > payload.account_id > cloud user_id mapping
        account_id = payload.get("local_account_id") or payload.get("account_id")
        cloud_user_id = job.get("user_id") or job.get("UserID")

        if account_id is None and cloud_user_id is not None:
            try:
                cloud_uid = int(cloud_user_id)
            except (TypeError, ValueError):
                cloud_uid = 0
            if cloud_uid > 0:
                local_id = _lookup_local_account_id(cloud_uid)
                if local_id is not None:
                    account_id = local_id
                else:
                    await self._report_fail(
                        job_id,
                        f"no local account mapped to cloud user_id={cloud_uid}",
                        "LOCAL_ACCOUNT_NOT_MAPPED",
                    )
                    return

        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            await self._report_fail(job_id, "missing local account id", "LOCAL_ACCOUNT_MISSING")
            return

        try:
            task_type = TaskType(task_type_value)
        except Exception:
            await self._report_fail(job_id, f"unsupported task_type: {task_type_value}", "TASK_TYPE_INVALID")
            return

        # Fetch full config from cloud for this user
        full_config = {}
        if cloud_user_id is not None:
            try:
                full_config = await cloud_api_client.get_full_config(
                    user_id=int(cloud_user_id),
                    token=self._agent_token,
                )
            except Exception as exc:
                self.log.warning(f"get_full_config failed for user_id={cloud_user_id}: {exc}")

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
        enqueued = executor_service.enqueue(
            account_id=account_id,
            task_type=task_type,
            payload=intent_payload,
        )
        if not enqueued:
            await cloud_api_client.report_job_heartbeat(
                agent_token=self._agent_token,
                node_id=self._node_id,
                job_id=job_id,
                lease_seconds=self._lease_seconds,
                message="local queue busy, keep lease",
            )
            return

        async with self._map_lock:
            self._account_jobs[account_id].append(job_id)

        await cloud_api_client.report_job_start(
            agent_token=self._agent_token,
            node_id=self._node_id,
            job_id=job_id,
            lease_seconds=self._lease_seconds,
            message=f"queued local account {account_id}",
        )

    async def _on_batch_done(
        self,
        account_id: int,
        success: bool,
        intents: List[TaskIntent],
    ) -> None:
        if not self._running:
            return
        async with self._map_lock:
            queue = self._account_jobs.get(account_id, deque())
            job_ids = list(queue)
            queue.clear()
            if not queue:
                self._account_jobs.pop(account_id, None)

        if not job_ids:
            return

        task_names = [intent.task_type.value for intent in intents]
        message = f"local batch done, account={account_id}, tasks={task_names}"
        for job_id in job_ids:
            try:
                if success:
                    await cloud_api_client.report_job_complete(
                        agent_token=self._agent_token,
                        node_id=self._node_id,
                        job_id=job_id,
                        message=message,
                    )
                else:
                    await cloud_api_client.report_job_fail(
                        agent_token=self._agent_token,
                        node_id=self._node_id,
                        job_id=job_id,
                        message=message,
                        error_code="LOCAL_BATCH_FAILED",
                    )
            except Exception as exc:
                self.log.warning(f"report cloud job result failed: job_id={job_id}, err={exc}")

        # Clear current_task on cloud after batch completes
        cloud_uid = None
        for intent in intents:
            if hasattr(intent, "payload") and isinstance(intent.payload, dict):
                cloud_uid = intent.payload.get("cloud_user_id")
                if cloud_uid:
                    break

        if cloud_uid:
            try:
                await cloud_api_client.update_game_profile(
                    user_id=int(cloud_uid),
                    fields={"current_task": ""},
                    token=self._agent_token,
                )
            except Exception as exc:
                self.log.warning(f"post-job cloud update failed for user_id={cloud_uid}: {exc}")

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
