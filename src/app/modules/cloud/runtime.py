"""
Cloud/local runtime state.
"""
from __future__ import annotations

from threading import Lock
from typing import Optional, Tuple

from ...core.config import settings


class RuntimeModeState:
    def __init__(self) -> None:
        mode = (settings.run_mode or "local").strip().lower()
        self._mode = "cloud" if mode == "cloud" else "local"
        self._manager_username = (settings.cloud_manager_username or "").strip()
        self._manager_password = settings.cloud_manager_password or ""
        self._manager_type = "all"
        self._scheduler_type = "all"
        self._lock = Lock()

    def get_mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> str:
        normalized = (mode or "local").strip().lower()
        if normalized not in {"local", "cloud"}:
            normalized = "local"
        with self._lock:
            self._mode = normalized
            return self._mode

    def is_cloud(self) -> bool:
        return self.get_mode() == "cloud"

    def set_manager_credentials(self, username: str, password: str) -> None:
        with self._lock:
            self._manager_username = (username or "").strip()
            self._manager_password = password or ""

    def get_manager_credentials(self) -> Tuple[str, str]:
        with self._lock:
            return self._manager_username, self._manager_password

    def clear_manager_credentials(self) -> None:
        with self._lock:
            self._manager_username = ""
            self._manager_password = ""

    def get_manager_username(self) -> Optional[str]:
        username, _ = self.get_manager_credentials()
        return username or None

    def set_manager_type(self, manager_type: str) -> None:
        with self._lock:
            self._manager_type = (manager_type or "all").strip().lower()

    def get_manager_type(self) -> str:
        with self._lock:
            return self._manager_type

    def set_scheduler_type(self, scheduler_type: str) -> None:
        with self._lock:
            self._scheduler_type = (scheduler_type or "all").strip().lower()

    def get_scheduler_type(self) -> str:
        with self._lock:
            return self._scheduler_type


runtime_mode_state = RuntimeModeState()


__all__ = ["runtime_mode_state", "RuntimeModeState"]
