"""
Scan task poller: 独立轮询扫码任务，分配给 scan 角色模拟器执行。
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

from ...core.constants import WorkerRole
from ...core.logger import logger
from ...db.base import SessionLocal
from ...db.models import Emulator, SystemConfig
from ..emu.adapter import AdapterConfig, EmulatorAdapter
from ..emu.async_adapter import AsyncEmulatorAdapter
from .client import cloud_api_client
from .runtime import runtime_mode_state


class ScanCancelledException(Exception):
    """扫码被取消异常"""
    pass


class ScanTaskPoller:
    """扫码任务专用轮询器，独立于常规任务轮询。"""

    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._agent_token: str = ""
        self._node_id: str = ""
        self._poll_interval = 3
        self._lease_seconds = 120
        self._active_scans: Dict[int, asyncio.Task] = {}  # scan_job_id -> task
        self._busy_emulators: set = set()  # 正在执行扫码的模拟器ID集合
        self.log = logger.bind(module="ScanTaskPoller")

    def _resolve_node_id(self) -> str:
        from .poller import _resolve_node_id
        return _resolve_node_id()

    async def start(self) -> None:
        if self._running:
            return
        if not cloud_api_client.configured():
            self.log.warning("CLOUD_API_BASE_URL 未配置，跳过 ScanTaskPoller 启动")
            return

        username, password = runtime_mode_state.get_manager_credentials()
        if not username or not password:
            self.log.warning("云端凭据未配置，跳过 ScanTaskPoller 启动")
            return

        self._node_id = self._resolve_node_id()
        self._agent_token = await cloud_api_client.agent_login(
            username=username, password=password, node_id=self._node_id,
        )
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.log.info("ScanTaskPoller started, node_id={}", self._node_id)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        # 取消所有活跃扫码任务
        for scan_id, task in self._active_scans.items():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._active_scans.clear()
        self._busy_emulators.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.log.info("ScanTaskPoller stopped")

    def _get_scan_emulators(self) -> list:
        """获取 role=scan 的模拟器列表"""
        with SessionLocal() as db:
            emulators = db.query(Emulator).filter(
                Emulator.role == WorkerRole.SCAN.value
            ).all()
            for e in emulators:
                db.expunge(e)
            return emulators

    def _get_idle_scan_emulator(self) -> Optional[Emulator]:
        """获取空闲的 scan 模拟器"""
        emulators = self._get_scan_emulators()
        for emu in emulators:
            if emu.id not in self._busy_emulators:
                return emu
        return None

    async def _loop(self) -> None:
        while self._running:
            try:
                # 检查是否有空闲的 scan 模拟器
                idle_emu = self._get_idle_scan_emulator()
                if not idle_emu:
                    await asyncio.sleep(self._poll_interval)
                    continue

                # token 过期重新登录
                if not self._agent_token:
                    username, password = runtime_mode_state.get_manager_credentials()
                    self._agent_token = await cloud_api_client.agent_login(
                        username=username, password=password, node_id=self._node_id,
                    )

                # 拉取扫码任务
                jobs = await cloud_api_client.scan_poll(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    limit=1,  # 每次只拉一个
                    lease_seconds=self._lease_seconds,
                )

                if not jobs:
                    await asyncio.sleep(self._poll_interval)
                    continue

                job = jobs[0]
                scan_id = int(job.get("scan_job_id") or job.get("id") or job.get("ID") or 0)
                if scan_id <= 0:
                    continue

                # 分配给空闲模拟器
                self._busy_emulators.add(idle_emu.id)
                scan_task = asyncio.create_task(
                    self._execute_scan(scan_id, job, idle_emu)
                )
                self._active_scans[scan_id] = scan_task

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.warning(f"scan poll error: {exc}")
                if "401" in str(exc) or "invalid token" in str(exc).lower():
                    self._agent_token = ""
                await asyncio.sleep(min(15, self._poll_interval * 2))

    async def _execute_scan(self, scan_id: int, job: dict, emulator: Emulator) -> None:
        """在指定模拟器上执行扫码任务"""
        try:
            # 上报开始
            await cloud_api_client.scan_start(
                agent_token=self._agent_token,
                node_id=self._node_id,
                scan_id=scan_id,
                lease_seconds=self._lease_seconds,
            )

            # 创建并运行 ScanQRExecutor
            from ..executor.scan_qr import ScanQRExecutor

            with SessionLocal() as db:
                syscfg = db.query(SystemConfig).first()
                if syscfg:
                    db.expunge(syscfg)

            executor = ScanQRExecutor(
                worker_id=emulator.id,
                emulator_id=emulator.id,
                emulator_row=emulator,
                system_config=syscfg,
                scan_job_id=scan_id,
                login_id=job.get("login_id", ""),
                cloud_client=cloud_api_client,
                agent_token=self._agent_token,
                node_id=self._node_id,
                lease_seconds=self._lease_seconds,
            )

            # 不使用标准的 run_task 流程（扫码是交互式的）
            await executor.run_scan()

        except ScanCancelledException:
            self.log.info(f"扫码任务被取消: scan_id={scan_id}")
            try:
                await cloud_api_client.scan_fail(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    scan_id=scan_id,
                    message="扫码被取消",
                    error_code="CANCELLED",
                )
            except Exception:
                pass
        except Exception as exc:
            self.log.error(f"扫码任务异常: scan_id={scan_id}, error={exc}")
            try:
                await cloud_api_client.scan_fail(
                    agent_token=self._agent_token,
                    node_id=self._node_id,
                    scan_id=scan_id,
                    message=str(exc)[:200],
                    error_code="EXECUTOR_ERROR",
                )
            except Exception:
                pass
        finally:
            self._busy_emulators.discard(emulator.id)
            self._active_scans.pop(scan_id, None)


scan_task_poller = ScanTaskPoller()
