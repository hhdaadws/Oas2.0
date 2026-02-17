# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 - YYS Automation 打包配置
使用方式：python -m PyInstaller --clean --noconfirm yys_automation.spec
"""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

a = Analysis(
    ['launcher.py'],
    pathex=[str(ROOT / 'src')],
    binaries=[],
    datas=[
        # 前端 build 产物
        (str(ROOT / 'frontend' / 'dist'), 'frontend_dist'),
        # 游戏资产（模板图片、YAML 任务配置）
        (str(ROOT / 'assets'), 'assets'),
        # OCR 模型
        (str(ROOT / 'ocr_model'), 'ocr_model'),
        # .env 示例
        (str(ROOT / '.env.example'), '.'),
    ],
    hiddenimports=[
        # ── uvicorn 动态导入 ──
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',

        # ── pywebview（桌面窗口）──
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',

        # ── PaddlePaddle / PaddleOCR ──
        'paddle',
        'paddle.base',
        'paddle.dataset',
        'paddleocr',
        'paddlex',
        'paddlex.pipelines',

        # ── ddddocr ──
        'ddddocr',

        # ── OpenCV ──
        'cv2',

        # ── SQLAlchemy ──
        'sqlalchemy.dialects.sqlite',

        # ── Pydantic ──
        'pydantic',
        'pydantic_settings',

        # ── 应用入口模块 ──
        'app.main',
        'app.core.config',
        'app.core.logger',
        'app.db',
        'app.db.models',

        # ── Web 路由 ──
        'app.modules.web',
        'app.modules.web.routers.auth',
        'app.modules.web.routers.accounts',
        'app.modules.web.routers.tasks',
        'app.modules.web.routers.dashboard',
        'app.modules.web.routers.emulators',
        'app.modules.web.routers.emulators_test',
        'app.modules.web.routers.system',
        'app.modules.web.routers.executor',
        'app.modules.web.routers.account_pull',
        'app.modules.web.routers.coop',
        'app.modules.web.routers.coop_extra',

        # ── 执行器 ──
        'app.modules.executor.service',
        'app.modules.executor.worker',
        'app.modules.executor.base',
        'app.modules.executor.helpers',
        'app.modules.executor.task_types',
        'app.modules.executor.yaml_loader',
        'app.modules.executor.add_friend',
        'app.modules.executor.battle',
        'app.modules.executor.climb_tower',
        'app.modules.executor.collect_login_gift',
        'app.modules.executor.collect_mail',
        'app.modules.executor.delegate_help',
        'app.modules.executor.digui',
        'app.modules.executor.explore',
        'app.modules.executor.explore_chapter',
        'app.modules.executor.init_executor',
        'app.modules.executor.init_exp_dungeon',
        'app.modules.executor.init_fanhe_upgrade',
        'app.modules.executor.init_rent_shikigami',
        'app.modules.executor.init_shikigami_train',
        'app.modules.executor.init_newbie_quest',
        'app.modules.executor.init_collect_reward',
        'app.modules.executor.init_collect_jinnang',
        'app.modules.executor.liao_coin',
        'app.modules.executor.liao_shop',
        'app.modules.executor.lineup_switch',
        'app.modules.executor.miwen',
        'app.modules.executor.signin',
        'app.modules.executor.summon_gift',
        'app.modules.executor.weekly_share',
        'app.modules.executor.weekly_shop',
        'app.modules.executor.xuanshang',
        'app.modules.executor.yuhun',
        'app.modules.executor.awaken',
        'app.modules.executor.collect_fanhe_jiuhu',
        'app.modules.executor.collect_achievement',
        'app.modules.executor.resource_check',

        # ── OCR ──
        'app.modules.ocr.engine',
        'app.modules.ocr.recognize',

        # ── 调度 ──
        'app.modules.tasks.feeder',

        # ── 其他依赖 ──
        'multiprocessing',
        'multiprocessing.popen_spawn_win32',
        'yaml',
        'aiofiles',
        'httpx',
        'apscheduler',
        'pyotp',
        'jwt',
        'loguru',
        'tenacity',
        'dateutil',
    ],
    hookspath=[str(ROOT / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型模块以减小体积
        'tkinter',
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'black',
        'flake8',
        'paddle.distributed',
        'paddle.incubate',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YYSAutomation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YYSAutomation',
)
