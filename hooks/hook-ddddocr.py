"""PyInstaller hook for ddddocr."""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('ddddocr')
