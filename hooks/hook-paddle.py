"""PyInstaller hook for PaddlePaddle."""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('paddle')

# 过滤掉不需要的大型子模块以减小打包体积
_exclude = {'distributed', 'incubate'}
hiddenimports = [
    m for m in hiddenimports
    if not any(f'paddle.{ex}' in m for ex in _exclude)
]
