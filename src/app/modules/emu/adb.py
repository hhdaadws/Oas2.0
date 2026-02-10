"""
ADB 适配封装

基于 SystemConfig 的 adb_path，提供基础操作：
- connect(addr)
- devices()
- screencap(addr) -> PNG bytes
- tap(addr, x, y)
- swipe(addr, x1, y1, x2, y2, dur_ms)
- start_app_monkey(addr, pkg)
- start_app_intent(addr, pkg)
- force_stop(addr, pkg)
"""
from __future__ import annotations

import subprocess
from typing import List


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, adb_path: str = "adb") -> None:
        self.adb = adb_path

    def _run(self, args: List[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
        try:
            cp = subprocess.run(
                [self.adb, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise AdbError(f"找不到 ADB 可执行文件: {self.adb}") from e
        return cp

    def connect(self, addr: str, timeout: float = 10.0) -> bool:
        cp = self._run(["connect", addr], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore").lower()
        return cp.returncode == 0 and ("connected" in out or "already" in out)

    def devices(self, timeout: float = 10.0) -> List[str]:
        cp = self._run(["devices"], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore").splitlines()
        result = []
        for line in out:
            line = line.strip()
            if not line or line.startswith("list of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                result.append(parts[0])
        return result

    def screencap(self, addr: str, timeout: float = 15.0) -> bytes:
        try:
            out = subprocess.check_output(
                [self.adb, "-s", addr, "exec-out", "screencap", "-p"],
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            return out
        except FileNotFoundError as e:
            raise AdbError(f"找不到 ADB 可执行文件: {self.adb}") from e
        except subprocess.CalledProcessError as e:
            raise AdbError((e.output or b"").decode(errors="ignore")) from e
        except subprocess.TimeoutExpired as e:
            raise AdbError("ADB 截图超时") from e

    def tap(self, addr: str, x: int, y: int, timeout: float = 10.0) -> None:
        cp = self._run(["-s", addr, "shell", "input", "tap", str(x), str(y)], timeout=timeout)
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def swipe(self, addr: str, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300, timeout: float = 10.0) -> None:
        cp = self._run(
            ["-s", addr, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur_ms)],
            timeout=timeout,
        )
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def start_app_monkey(self, addr: str, pkg: str, timeout: float = 10.0, fallback_activity: str | None = None) -> None:
        cp = self._run([
            "-s", addr, "shell", "monkey",
            "-p", pkg,
            "-c", "android.intent.category.LAUNCHER",
            "1"
        ], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore").lower() + (cp.stderr or b"").decode(errors="ignore").lower()
        # monkey 返回码可能为 0 但未真正注入事件，仅打印 args/data；检测不到 "events injected" 则尝试 am start
        if cp.returncode != 0 or ("events injected" not in out):
            # 尝试使用显式组件名启动
            if fallback_activity:
                cp2 = self._run([
                    "-s", addr, "shell", "am", "start",
                    "-a", "android.intent.action.MAIN",
                    "-c", "android.intent.category.LAUNCHER",
                    "-n", f"{pkg}/{fallback_activity}"
                ], timeout=timeout)
                if cp2.returncode == 0:
                    return
            # 若无 activity 或失败，尝试仅以包名 + MAIN/LAUNCHER 启动
            cp3 = self._run([
                "-s", addr, "shell", "am", "start",
                "-a", "android.intent.action.MAIN",
                "-c", "android.intent.category.LAUNCHER",
                pkg
            ], timeout=timeout)
            if cp3.returncode != 0:
                raise AdbError((cp3.stderr or b"").decode(errors="ignore"))

    def start_app_intent(self, addr: str, pkg: str, activity: str | None = None, timeout: float = 10.0) -> None:
        # 若未提供显式 activity，使用 package 的默认 LAUNCHER Activity
        args = ["-s", addr, "shell", "am", "start", "-n", f"{pkg}/{activity}" ] if activity else [
            "-s", addr, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{pkg}/.MainActivity"
        ]
        # 注意：实际活动名可能不同，调用方可传 activity 覆盖；未命中时系统可能仍能通过 MAIN/LAUNCHER 打开
        cp = self._run(args, timeout=timeout)
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def start_app_am_component(self, addr: str, pkg: str, activity: str, timeout: float = 10.0) -> None:
        # 仅使用显式组件，不附加 MAIN/LAUNCHER flags
        if not activity:
            raise AdbError("am start 需要显式 activity 名称")
        cp = self._run(["-s", addr, "shell", "am", "start", "-n", f"{pkg}/{activity}"], timeout=timeout)
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def start_app_main_launcher(self, addr: str, pkg: str, timeout: float = 10.0) -> None:
        cp = self._run([
            "-s", addr, "shell", "am", "start",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            pkg
        ], timeout=timeout)
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def is_app_running(self, addr: str, pkg: str, timeout: float = 5.0) -> bool:
        # Try pidof first
        cp = self._run(["-s", addr, "shell", "pidof", pkg], timeout=timeout)
        if cp.returncode == 0:
            out = (cp.stdout or b"").decode(errors="ignore").strip()
            if out:
                return True
        # Fallback to ps | grep
        cp2 = self._run(["-s", addr, "shell", "sh", "-c", f"ps | grep -w {pkg} | grep -v grep"], timeout=timeout)
        if cp2.returncode == 0:
            out2 = (cp2.stdout or b"").decode(errors="ignore").strip()
            return bool(out2)
        return False

    def wait_for_app_running(self, addr: str, pkg: str, timeout_total: float = 12.0, interval: float = 0.5) -> bool:
        import time
        end = time.time() + timeout_total
        while time.time() < end:
            if self.is_app_running(addr, pkg):
                return True
            time.sleep(interval)
        return False

    def list_packages(self, addr: str, pattern: str = "onmyoji", timeout: float = 10.0) -> list[str]:
        cp = self._run(["-s", addr, "shell", "pm", "list", "packages"], timeout=timeout)
        if cp.returncode != 0:
            return []
        out = (cp.stdout or b"").decode(errors="ignore").splitlines()
        pkgs: list[str] = []
        for line in out:
            line = line.strip()
            if not line:
                continue
            if line.startswith("package:"):
                name = line.split(":", 1)[1]
                if not pattern or pattern.lower() in name.lower():
                    pkgs.append(name)
        return pkgs

    def resolve_launcher_component(self, addr: str, pkg: str, timeout: float = 10.0) -> str | None:
        """解析包的 MAIN/LAUNCHER 入口，返回形如 'com.pkg/.MainActivity' 的组件字符串。
        先尝试 cmd package resolve-activity --brief，失败回退 dumpsys/pm dump 简单解析。
        """
        # 方式1：cmd package resolve-activity --brief
        cp = self._run([
            "-s", addr, "shell", "cmd", "package", "resolve-activity",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            pkg, "--brief"
        ], timeout=timeout)
        if cp.returncode == 0:
            out = (cp.stdout or b"").decode(errors="ignore").strip()
            # 可能包含多行，取第一行包含 pkg 的
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                if pkg in line and "/" in line:
                    return line

        # 方式2：dumpsys package pkg 简易解析（找含 MAIN/LAUNCHER 的 activity）
        cp2 = self._run(["-s", addr, "shell", "dumpsys", "package", pkg], timeout=timeout)
        if cp2.returncode == 0:
            text = (cp2.stdout or b"").decode(errors="ignore")
            # 简易正则：匹配 activity 名称，附近带有 MAIN 和 LAUNCHER 的 filter
            import re
            # 寻找 LAUNCHER activity 声明块
            # 先找所有形如 'ActivityResolver' 的候选太复杂，做一个简化：
            # 寻找行包含 pkg/ 和 'LAUNCHER' 附近的组件
            m = re.search(r"(\S+/\S+)(?=.*LAUNCHER)", text, re.IGNORECASE | re.DOTALL)
            if m:
                comp = m.group(1)
                if pkg in comp and "/" in comp:
                    return comp
        return None

    def force_stop(self, addr: str, pkg: str, timeout: float = 10.0) -> None:
        cp = self._run(["-s", addr, "shell", "am", "force-stop", pkg], timeout=timeout)
        if cp.returncode != 0:
            raise AdbError((cp.stderr or b"").decode(errors="ignore"))

    def root(self, addr: str, timeout: float = 10.0) -> bool:
        """执行 adb root 获取权限"""
        cp = self._run(["-s", addr, "root"], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore").lower()
        # root 成功会输出 "restarting adbd as root" 或 "adbd is already running as root"
        return cp.returncode == 0 or "root" in out

    def push(self, addr: str, local_path: str, remote_path: str, timeout: float = 60.0) -> tuple[bool, str]:
        """推送本地文件/文件夹到设备"""
        cp = self._run(["-s", addr, "push", local_path, remote_path], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore")
        err = (cp.stderr or b"").decode(errors="ignore")
        if cp.returncode == 0:
            return True, out
        return False, err or out

    def shell(self, addr: str, cmd: str, timeout: float = 10.0) -> tuple[int, str]:
        """执行 adb shell 命令，返回 (returncode, output)"""
        cp = self._run(["-s", addr, "shell", cmd], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore")
        return cp.returncode, out

    def pull(self, addr: str, remote_path: str, local_path: str, timeout: float = 60.0) -> tuple[bool, str]:
        """从设备拉取文件/文件夹到本地"""
        cp = self._run(["-s", addr, "pull", remote_path, local_path], timeout=timeout)
        out = (cp.stdout or b"").decode(errors="ignore")
        err = (cp.stderr or b"").decode(errors="ignore")
        if cp.returncode == 0:
            return True, out
        return False, err or out
