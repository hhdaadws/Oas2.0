"""PyInstaller hook for PaddlePaddle."""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('paddle')
hiddenimports += collect_submodules('paddle')
