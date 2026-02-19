"""
Cloud API client for runtime polling/reporting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ...core.config import settings


class CloudApiError(RuntimeError):
    """Cloud API request failed."""


class CloudApiClient:
    def __init__(self) -> None:
        self._base_url = (settings.cloud_api_base_url or "").rstrip("/")
        self._timeout = max(3, int(settings.cloud_timeout_sec or 15))

    def configured(self) -> bool:
        return bool(self._base_url)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            raise CloudApiError("CLOUD_API_BASE_URL 未配置")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method=method,
                url=self._url(path),
                json=json_data,
                headers=headers,
            )
        try:
            payload = response.json()
        except Exception:
            payload = {"detail": response.text}
        if response.status_code >= 400:
            detail = payload.get("detail") or payload.get("message") or response.text
            raise CloudApiError(f"{response.status_code}: {detail}")
        return payload

    async def manager_login(self, username: str, password: str) -> str:
        payload = await self._request(
            "POST",
            "/api/v1/manager/auth/login",
            {"username": username, "password": password},
        )
        token = payload.get("token")
        if not token:
            raise CloudApiError("云端管理员登录未返回 token")
        return token

    async def agent_login(
        self, username: str, password: str, node_id: str, version: str = "1.0.0"
    ) -> str:
        payload = await self._request(
            "POST",
            "/api/v1/agent/auth/login",
            {
                "username": username,
                "password": password,
                "node_id": node_id,
                "version": version,
            },
        )
        token = payload.get("token")
        if not token:
            raise CloudApiError("云端 agent 登录未返回 token")
        return token

    async def poll_jobs(
        self,
        agent_token: str,
        node_id: str,
        limit: int,
        lease_seconds: int,
    ) -> List[Dict[str, Any]]:
        payload = await self._request(
            "POST",
            "/api/v1/agent/poll-jobs",
            {
                "node_id": node_id,
                "limit": limit,
                "lease_seconds": lease_seconds,
            },
            token=agent_token,
        )
        jobs = payload.get("jobs") or []
        if not isinstance(jobs, list):
            return []
        return jobs

    async def report_job_start(
        self,
        agent_token: str,
        node_id: str,
        job_id: int,
        lease_seconds: int,
        message: str = "",
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agent/jobs/{job_id}/start",
            {
                "node_id": node_id,
                "lease_seconds": lease_seconds,
                "message": message,
            },
            token=agent_token,
        )

    async def report_job_heartbeat(
        self,
        agent_token: str,
        node_id: str,
        job_id: int,
        lease_seconds: int,
        message: str = "",
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agent/jobs/{job_id}/heartbeat",
            {
                "node_id": node_id,
                "lease_seconds": lease_seconds,
                "message": message,
            },
            token=agent_token,
        )

    async def report_job_complete(
        self,
        agent_token: str,
        node_id: str,
        job_id: int,
        message: str = "completed",
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agent/jobs/{job_id}/complete",
            {
                "node_id": node_id,
                "message": message,
            },
            token=agent_token,
        )

    async def report_job_fail(
        self,
        agent_token: str,
        node_id: str,
        job_id: int,
        message: str = "failed",
        error_code: str = "LOCAL_EXEC_FAIL",
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/agent/jobs/{job_id}/fail",
            {
                "node_id": node_id,
                "message": message,
                "error_code": error_code,
            },
            token=agent_token,
        )

    async def get_full_config(self, user_id: int, token: str) -> Dict[str, Any]:
        """Get user's full config: task_config + rest_config + lineup_config + shikigami_config + explore_progress"""
        payload = await self._request(
            "GET",
            f"/api/v1/agent/users/{user_id}/full-config",
            token=token,
        )
        return payload

    async def update_game_profile(self, user_id: int, fields: Dict[str, Any], token: str) -> None:
        """Update account_status / current_task / progress"""
        await self._request(
            "PATCH",
            f"/api/v1/agent/users/{user_id}/game-profile",
            json_data=fields,
            token=token,
        )

    async def update_explore_progress(self, user_id: int, progress: Dict[str, Any], token: str) -> None:
        """Update explore progress after task execution"""
        await self._request(
            "PUT",
            f"/api/v1/agent/users/{user_id}/explore-progress",
            json_data={"progress": progress},
            token=token,
        )

    async def report_logs(self, user_id: int, logs: List[Dict[str, Any]], token: str) -> None:
        """Batch upload execution logs [{type, level, message, ts}]"""
        await self._request(
            "POST",
            f"/api/v1/agent/users/{user_id}/logs",
            json_data={"logs": logs},
            token=token,
        )


cloud_api_client = CloudApiClient()


__all__ = ["CloudApiClient", "CloudApiError", "cloud_api_client"]
