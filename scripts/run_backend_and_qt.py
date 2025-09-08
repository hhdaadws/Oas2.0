"""
集成启动后端 (uvicorn) 与 PyQt6 窗口（内嵌 Dashboard）。

用法：
  pip install -r requirements.txt
  pip install PyQt6 PyQt6-WebEngine
  python scripts/run_backend_and_qt.py --reload   # 如需热重载可加 --reload

可选参数：
  --backend-host  默认 127.0.0.1
  --backend-port  默认 9001
  --frontend-url  默认 http://localhost:9000/dashboard
  --reload        启动 uvicorn --reload
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from contextlib import suppress


def wait_for_http(url: str, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """等待 url 可访问，直到超时。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(interval)
    return False


def start_backend(host: str, port: int, reload: bool) -> subprocess.Popen:
    """启动 uvicorn 后端并返回进程句柄。"""
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "src",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")

    print("[Runner] Starting backend:", " ".join(cmd))
    # Windows 下关闭窗口时也能结束子进程；避免使用 shell=True
    proc = subprocess.Popen(cmd)
    return proc


def stop_process(proc: subprocess.Popen) -> None:
    if proc is None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            with suppress(ProcessLookupError):
                proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(Exception):
                proc.kill()
    except Exception:
        pass


def _build_app_icon() -> "QIcon":
    """使用 PyQt6 动态生成一个 ICO 图标并返回 QIcon。

    图标风格：蓝紫渐变背景，白色“云”字。并尝试保存到 assets/app.ico。
    """
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QLinearGradient, QColor, QFont
    from PyQt6.QtCore import Qt
    import os

    size = 256
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    try:
        # 背景渐变
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor(74, 119, 255))   # 蓝色
        grad.setColorAt(1.0, QColor(139, 92, 246))   # 紫色
        painter.fillRect(0, 0, size, size, grad)

        # 白色大字“云”
        font = QFont("Microsoft YaHei", int(size * 0.55))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        text = "云"
        rect = pm.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    finally:
        painter.end()

    icon = QIcon(pm)

    # 尝试保存 ICO 文件供外部使用
    try:
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        os.makedirs(assets_dir, exist_ok=True)
        pm.save(os.path.join(assets_dir, "app.ico"), "ICO")
    except Exception:
        pass

    return icon


def run_qt(url: str) -> int:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication(sys.argv)
    app.setApplicationName("云韵阴阳师")

    # 设置应用与窗口图标
    try:
        icon = _build_app_icon()
        app.setWindowIcon(icon)
    except Exception:
        icon = None

    view = QWebEngineView()
    view.setWindowTitle("云韵阴阳师")
    if icon is not None:
        try:
            view.setWindowIcon(icon)
        except Exception:
            pass

    view.resize(1280, 800)
    view.load(QUrl(url))
    view.show()
    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend and PyQt6 dashboard window")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=9001)
    parser.add_argument("--frontend-url", default="http://localhost:9000/dashboard")
    parser.add_argument("--reload", action="store_true", help="Run uvicorn with --reload")
    args = parser.parse_args()

    backend_proc: subprocess.Popen | None = None
    try:
        backend_proc = start_backend(args.backend_host, args.backend_port, args.reload)

        # 等待后端健康检查可用
        health_url = f"http://{args.backend_host}:{args.backend_port}/health"
        print(f"[Runner] Waiting for backend: {health_url}")
        if not wait_for_http(health_url, timeout=30):
            print("[Runner] Backend not ready within 30s, continuing anyway...")

        # 启动 Qt 窗口
        print(f"[Runner] Opening dashboard: {args.frontend_url}")
        exit_code = run_qt(args.frontend_url)
        return exit_code
    except KeyboardInterrupt:
        return 0
    except ImportError as e:
        print("[Runner] Missing PyQt6 dependencies. Please install: pip install PyQt6 PyQt6-WebEngine")
        print(e)
        return 1
    finally:
        stop_process(backend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
