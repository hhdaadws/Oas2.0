"""PyInstaller hook for PaddleX (PaddleOCR 3.x 内部依赖)。"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('paddlex')
