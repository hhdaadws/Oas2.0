"""
一键打包脚本。
Usage: python build.py
"""
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "YYSAutomation"

# Conda 环境路径（PyInstaller 需要从此环境运行，因为依赖都在这里）
CONDA_ENV = Path(r"D:\Users\ASUS\anaconda3\envs\timeocr")
CONDA_PYTHON = CONDA_ENV / "python.exe"


def step(msg: str):
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}")


def build_frontend():
    step("1/3  构建前端 (npm run build)")
    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "node_modules").exists():
        print("  安装前端依赖...")
        subprocess.check_call(
            ["npm", "install"], cwd=str(frontend_dir), shell=True
        )
    subprocess.check_call(
        ["npm", "run", "build"], cwd=str(frontend_dir), shell=True
    )
    dist_dir = frontend_dir / "dist"
    if not (dist_dir / "index.html").exists():
        print("[ERROR] 前端构建失败：未找到 dist/index.html")
        sys.exit(1)
    print("  前端构建完成")


def build_pyinstaller():
    step("2/3  PyInstaller 打包")
    spec_file = ROOT / "yys_automation.spec"
    if not spec_file.exists():
        print(f"[ERROR] 未找到 spec 文件: {spec_file}")
        sys.exit(1)
    if not CONDA_PYTHON.exists():
        print(f"[ERROR] 未找到 Conda Python: {CONDA_PYTHON}")
        print("  请修改 build.py 中的 CONDA_ENV 路径")
        sys.exit(1)
    subprocess.check_call([
        str(CONDA_PYTHON), "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ], cwd=str(ROOT))
    print("  PyInstaller 打包完成")


def post_process():
    step("3/3  后处理：调整运行时资源位置")

    # PyInstaller --onedir 将 datas 放在 _internal/ 下，
    # 需要将 assets、ocr_model、frontend_dist 移到 exe 旁边
    internal = DIST / "_internal"

    for dirname in ["assets", "ocr_model", "frontend_dist"]:
        src = internal / dirname
        dst = DIST / dirname
        if src.exists() and not dst.exists():
            print(f"  移动 {dirname} → exe 旁边")
            shutil.move(str(src), str(dst))
        elif dst.exists():
            print(f"  {dirname} 已存在，跳过")

    # 复制 .env.example 为 .env（如不存在）
    env_example = internal / ".env.example"
    if not env_example.exists():
        env_example = DIST / ".env.example"
    env_target = DIST / ".env"
    if env_example.exists() and not env_target.exists():
        shutil.copy2(str(env_example), str(env_target))
        print("  已创建 .env 文件")

    # 创建运行时需要的空目录
    for d in ["logs", "putonglogindata", "gouxielogindata"]:
        (DIST / d).mkdir(exist_ok=True)

    print("  后处理完成")


def main():
    build_frontend()
    build_pyinstaller()
    post_process()

    step("打包完成!")
    print(f"  输出目录: {DIST}")
    print(f"  启动命令: {DIST / 'YYSAutomation.exe'}")
    print()


if __name__ == "__main__":
    main()
