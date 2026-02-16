"""PyInstaller hook for PaddleOCR."""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('paddleocr')
hiddenimports += collect_submodules('paddleocr')
