"""
PyInstaller 打包入口。
双击 exe 后：设置 cwd → 后台启动 FastAPI → 打开桌面窗口。
"""
import sys
import os
import time
import threading
from pathlib import Path


def _get_app_dir() -> Path:
    """获取应用所在目录。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent


def _wait_for_backend(url: str, timeout: int = 30) -> bool:
    """等待后端就绪。"""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f"{url}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _start_server(host: str, port: int):
    """在后台线程中启动 uvicorn。"""
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    app_dir = _get_app_dir()

    # 设置 cwd 到应用目录，保证 assets/ 等相对路径有效
    os.chdir(app_dir)

    # 开发模式下确保 src 在 PYTHONPATH
    src_dir = str(app_dir / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    host = "127.0.0.1"
    port = 9001
    backend_url = f"http://{host}:{port}"

    print(f"[YYS Automation] 正在启动服务 {backend_url} ...")

    # 后台线程启动 uvicorn
    server_thread = threading.Thread(target=_start_server, args=(host, port), daemon=True)
    server_thread.start()

    # 等待后端就绪
    if not _wait_for_backend(backend_url, timeout=60):
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "后端启动超时，请检查日志", "YYS Automation", 0x10
        )
        return

    # 确定前端 URL：打包模式直接用后端（已挂载前端静态文件），
    # 开发模式优先检测 frontend/dist，不存在则使用 Vite dev server
    if getattr(sys, 'frozen', False):
        frontend_url = backend_url
    else:
        frontend_dist = app_dir / "frontend" / "dist"
        if (frontend_dist / "index.html").exists():
            frontend_url = backend_url
        else:
            frontend_url = f"http://{host}:9000"
            print(f"[YYS Automation] 前端未构建，使用 Vite dev server: {frontend_url}")

    print(f"[YYS Automation] 服务已就绪，正在打开窗口 → {frontend_url}")

    # 使用 pywebview 创建桌面窗口
    import webview

    window = webview.create_window(
        title="YYS Automation",
        url=frontend_url,
        width=1280,
        height=860,
        resizable=True,
        min_size=(800, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
