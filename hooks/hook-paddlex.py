"""PyInstaller hook for PaddleX (PaddleOCR 3.x 内部依赖)。"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('paddlex')
hiddenimports += collect_submodules('paddlex')
