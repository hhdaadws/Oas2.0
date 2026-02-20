#!/usr/bin/env python3
"""
一键打包脚本：前端构建 → PyInstaller → 后处理
输出到 dist/YYSAutomation/

CONDA_ENV 可通过环境变量设置，例如：
  set CONDA_ENV=D:\\Users\\ASUS\\anaconda3\\envs\\timeocr
  python build.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── 配置（优先从环境变量读取） ────────────────────────────────────────────────
CONDA_ENV = Path(os.environ.get(
    "CONDA_ENV", r"D:\Users\ASUS\anaconda3\envs\timeocr"
))
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent


def run(cmd, cwd=None, use_shell=False):
    """执行子进程命令。use_shell 仅在需要时（如 npm .cmd）启用。"""
    print(f"[BUILD] {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, cwd=cwd or ROOT, check=True, shell=use_shell)


def run_npm(args, cwd):
    """执行 npm 命令（Windows 上 npm 是 .cmd，需要 shell=True）。"""
    run(["npm"] + args, cwd=cwd, use_shell=True)


def get_python():
    py = CONDA_ENV / "python.exe"
    if py.exists():
        return str(py)
    print(f"[WARN] Conda env not found at {CONDA_ENV}, falling back to {sys.executable}")
    return sys.executable


def build_frontend():
    print("\n===== 1/3  前端构建 =====")
    frontend_dir = ROOT / "frontend"
    if not frontend_dir.exists():
        raise RuntimeError(f"前端目录不存在：{frontend_dir}")
    if not (frontend_dir / "node_modules").exists():
        run_npm(["install"], cwd=frontend_dir)
    run_npm(["run", "build"], cwd=frontend_dir)
    dist = frontend_dir / "dist"
    if not dist.exists():
        raise RuntimeError("前端构建失败：frontend/dist 不存在")
    if not (dist / "index.html").exists():
        raise RuntimeError("前端构建异常：frontend/dist/index.html 不存在")
    print(f"[BUILD] 前端构建完成：{dist}")


def build_pyinstaller():
    print("\n===== 2/3  PyInstaller 打包 =====")
    spec_file = ROOT / "yys_automation.spec"
    if not spec_file.exists():
        raise RuntimeError(f"spec 文件不存在：{spec_file}")
    run([get_python(), "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_file)])
    out = ROOT / "dist" / "YYSAutomation"
    if not out.exists():
        raise RuntimeError(f"PyInstaller 打包失败：{out} 不存在")
    # 验证打包产物包含前端文件
    frontend_dist = out / "frontend_dist"
    if not (frontend_dist / "index.html").exists():
        print(f"[WARN] 打包产物缺少前端文件：{frontend_dist / 'index.html'}")
    print(f"[BUILD] PyInstaller 完成：{out}")


def post_process():
    print("\n===== 3/3  后处理 =====")
    out = ROOT / "dist" / "YYSAutomation"
    env_example = ROOT / ".env.example"
    env_dest = out / ".env.example"
    if env_example.exists() and not env_dest.exists():
        shutil.copy2(env_example, env_dest)
        print(f"[BUILD] 复制 .env.example → {env_dest}")
    print(f"[BUILD] 后处理完成，输出目录：{out}")


def main():
    print("=" * 60)
    print("  YYS Automation 打包")
    print(f"  CONDA_ENV : {CONDA_ENV}")
    print(f"  Python    : {get_python()}")
    print(f"  ROOT      : {ROOT}")
    print("=" * 60)

    build_frontend()
    build_pyinstaller()
    post_process()

    print(f"\n===== 打包完成：{ROOT / 'dist' / 'YYSAutomation'} =====")


if __name__ == "__main__":
    main()
