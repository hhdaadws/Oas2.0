"""
MuMu 管理器封装（示例）

基于设计文档的命令示例，提供基本能力：
- launch(index)
- quit(index)
- adb(index) -> 端口或地址（按版本不同需适配）

说明：不同版本 MuMu 管理器命令和参数可能不同，这里提供占位与最常见方式。
"""
from __future__ import annotations

import subprocess
from typing import Optional


class MuMuManagerError(RuntimeError):
    pass


class MuMuManager:
    def __init__(self, manager_path: str) -> None:
        self.path = manager_path

    def _run(self, args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
        try:
            cp = subprocess.run([self.path, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except FileNotFoundError as e:
            raise MuMuManagerError(f"找不到 MuMuManager 可执行文件: {self.path}") from e
        return cp

    def launch(self, index: int) -> None:
        cp = self._run(["launch", "--index", str(index)])
        if cp.returncode != 0:
            raise MuMuManagerError((cp.stderr or b"").decode(errors="ignore"))

    def quit(self, index: int) -> None:
        cp = self._run(["quit", "--index", str(index)])
        if cp.returncode != 0:
            raise MuMuManagerError((cp.stderr or b"").decode(errors="ignore"))

    def adb_addr(self, index: int) -> Optional[str]:
        # 某些版本支持：MuMuManager.exe adb --index N → 输出端口
        cp = self._run(["adb", "--index", str(index)])
        if cp.returncode != 0:
            return None
        out = (cp.stdout or b"").decode(errors="ignore").strip()
        # 解析输出为端口或地址。这里假定输出端口，转换为 127.0.0.1:PORT
        try:
            port = int(out)
            return f"127.0.0.1:{port}"
        except Exception:
            # 也可能直接输出地址
            return out or None

